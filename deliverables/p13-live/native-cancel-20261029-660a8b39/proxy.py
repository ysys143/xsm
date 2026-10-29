"""Record exact stdio bytes for one real xsm server; no fan-in or rewriting."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

root = Path(sys.argv[1])
source = Path(sys.argv[2])
folder = root / 'proxies' / ('%s-%s' % (os.getpid(), uuid.uuid4().hex[:8]))
folder.mkdir(mode=0o700)


def info(pid):
    start = subprocess.run(['ps', '-o', 'lstart=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
    parent = subprocess.run(['ps', '-o', 'ppid=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
    name = subprocess.run(['ps', '-o', 'comm=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
    return {'pid': pid, 'ppid': int(parent) if parent else None, 'lstart': start or None, 'comm': name}


server = subprocess.Popen([sys.executable, '-m', 'xsm', 'mcp'], cwd=str(source),
                          env=dict(os.environ), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=(folder/'server.stderr').open('wb'))
chain = []
current = os.getpid()
for _ in range(10):
    row = info(current)
    chain.append(row)
    if Path(row['comm']).name == 'codex':
        break
    if not row['ppid']:
        break
    current = row['ppid']
(folder/'handles.json').write_text(json.dumps({'proxy': info(os.getpid()), 'server': info(server.pid),
                                              'native_ancestor_chain': chain}, indent=2)+'\n')
lock = threading.Lock()


def record(direction, line):
    with (folder/(direction+'-wire.jsonl')).open('ab') as stream:
        stream.write(line)
        stream.flush()
    value = json.loads(line)
    params = value.get('params') or {}
    event = {'at': time.time(), 'direction': direction, 'bytes': len(line),
             'sha256': hashlib.sha256(line).hexdigest(), 'id': value.get('id'),
             'method': value.get('method'), 'tool': params.get('name'),
             'actual_meta': params.get('_meta'), 'server_pid': server.pid}
    with lock, (folder/'events.jsonl').open('a') as stream:
        stream.write(json.dumps(event)+'\n')


def output():
    for line in server.stdout:
        record('server', line)
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()


reader = threading.Thread(target=output, daemon=True)
reader.start()
try:
    for line in sys.stdin.buffer:
        record('client', line)
        server.stdin.write(line)
        server.stdin.flush()
finally:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
    (folder/'exit.json').write_text(json.dumps({'server_returncode': server.returncode})+'\n')
