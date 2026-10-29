// 배포 CLI의 ask-worker 모듈을 수정하지 않고 격리된 가짜 자식 프로세스·네트워크로 실행한다.
import vm from 'node:vm';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { EventEmitter } from 'node:events';

const [modulePath, planPath] = process.argv.slice(2);
const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
fs.mkdirSync(plan.home, { recursive: true });
fs.mkdirSync(plan.cwd, { recursive: true });
let childId = 0;
let done = false;
let delivered = 0;
let attempts = 0;
const childRequests = new Map();
const failures = new Map();
const event = (type, fields = {}) => process.stdout.write(JSON.stringify({ type, at: Date.now(), ...fields }) + '\n');
const finish = () => {
  if (done) return;
  done = true;
  setTimeout(() => process.emit('SIGTERM'), 40);
};

class Child extends EventEmitter {
  constructor(command, argv) {
    super();
    this.id = ++childId;
    this.command = command;
    this.argv = argv;
    this.alive = true;
    this.prior = null;
    this.stdout = new EventEmitter(); this.stdout.setEncoding = () => {};
    this.stderr = new EventEmitter(); this.stderr.resume = () => {};
    this.stdin = { write: (line) => {
      const input = JSON.parse(line);
      this.answer(input.message.content, false);
      return true;
    }};
    event('spawn', { child: this.id, command, argv });
    if (command !== 'claude') this.answer(argv.at(-1), true);
  }
  answer(prompt, oneShot) {
    const match = /CASE:([A-Za-z0-9_-]+);/.exec(prompt);
    const id = match?.[1];
    const item = plan.catalog.find(x => x.id === id);
    if (!item) throw Error('unmapped fixture prompt');
    childRequests.set(id, (childRequests.get(id) ?? 0) + 1);
    event('ask_start', { id, child: this.id, prior: this.prior });
    const result = `fixture-answer:${id};child:${this.id};prior:${this.prior ?? 'none'}`;
    this.prior = id;
    setTimeout(() => {
      if (!this.alive) return;
      event('ask_end', { id, child: this.id });
      fs.appendFileSync(path.join(plan.home, 'simulated-effects.jsonl'), JSON.stringify({ id }) + '\n');
      if (plan.crashAt === 'after_work') process.exit(81);
      if (oneShot) {
        this.stdout.emit('data', JSON.stringify({ type: 'thread.started', thread_id: `fixture-${this.id}` }) + '\n');
        this.stdout.emit('data', JSON.stringify({ type: 'item.completed', item: { type: 'agent_message', text: result } }) + '\n');
        this.stdout.emit('data', JSON.stringify({ type: 'turn.completed' }) + '\n');
        this.emit('close', 0);
      } else this.stdout.emit('data', JSON.stringify({ type: 'result', result, session_id: `fixture-${this.id}` }) + '\n');
    }, item.delay ?? 5);
  }
  kill() {
    if (!this.alive) return;
    this.alive = false;
    event('kill', { child: this.id });
    this.emit('exit', 0);
  }
}

let batch = 0;
const session = {
  name: plan.name ?? 'worker', address: 'fixture/worker',
  idle: async (text) => {
    event('idle', { text });
    if (plan.stopAfterAttempts && attempts >= plan.stopAfterAttempts) finish();
  },
  busy: async text => event('busy', { text }),
  ack: async ids => {
    event('ack', { ids });
    if (plan.crashAt === 'ack') process.exit(77);
  },
  send: async (to, body, replyTo) => {
    attempts++;
    const n = (failures.get(replyTo) ?? 0) + 1;
    failures.set(replyTo, n);
    event('send_attempt', { to, body, replyTo, attempt: n });
    if (plan.crashAt === 'send') process.exit(78);
    if (n <= (plan.failSends ?? 0)) throw Error('fixture network failure');
    delivered++;
    event('reply', { to, body, replyTo });
    if (delivered >= plan.expectedReplies) finish();
  },
  next: async () => {
    if (plan.batches && batch < plan.batches.length) {
      const item = plan.batches[batch++];
      if (item.delay) await new Promise(r => setTimeout(r, item.delay));
      return item.ids.map(id => plan.catalog.find(x => x.id === id));
    }
    return new Promise(() => {});
  }
};
const processProxy = {
  env: {}, pid: process.pid,
  stderr: { write: text => event('worker_stderr', { text }) },
  stdout: { write: text => event('worker_stdout', { text }) },
  once: (name, callback) => process.once(name, callback),
  exit: code => process.exit(code),
  cwd: () => plan.cwd
};
const context = vm.createContext({ process: processProxy, setTimeout, clearTimeout, console, Buffer });
const dependencies = {
  child_process: { spawn: (command, argv) => new Child(command, argv) },
  crypto: { createHash: crypto.createHash },
  fs: {
    existsSync: fs.existsSync, mkdirSync: fs.mkdirSync, readdirSync: fs.readdirSync,
    readFileSync: fs.readFileSync, renameSync: fs.renameSync, writeFileSync: fs.writeFileSync
  },
  os: { homedir: () => plan.home },
  path: { join: path.join, sep: path.sep },
  helper: { na: message => message.body, w: String }
};
const module = new vm.SourceTextModule(fs.readFileSync(modulePath, 'utf8'), { context });
await module.link(async name => {
  const values = name.startsWith('/$bunfs/') ? dependencies.helper : dependencies[name];
  if (!values) throw Error(`unexpected worker import ${name}`);
  return new vm.SyntheticModule(Object.keys(values), function() {
    for (const [key, value] of Object.entries(values)) this.setExport(key, value);
  }, { context });
});
await module.evaluate();
event('module_loaded', { sha256: crypto.createHash('sha256').update(fs.readFileSync(modulePath)).digest('hex') });
const io = {
  stdout: { write: text => { event('worker_stdout', { text }); return true; } },
  stderr: { write: text => { event('worker_stderr', { text }); return true; } }
};
setTimeout(() => { event('fixture_watchdog_failed'); process.exit(79); }, 20000).unref();
module.namespace.serveAgent({ session: async () => session }, {
  agent: plan.agent ?? 'claude', name: session.name, cwd: plan.cwd, fullAccess: false, io
}).catch(error => { event('fixture_error', { error: error.stack }); process.exit(80); });
