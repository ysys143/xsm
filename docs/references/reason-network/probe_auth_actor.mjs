// 배포 모듈은 수정하지 않는다. 모든 HTTP·자격 증명·프로세스는 fixture다.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import vm from 'node:vm';
import crypto from 'node:crypto';
const [modulePath, output] = process.argv.slice(2);
const root = fs.mkdtempSync('/private/tmp/reason-auth-probe-');
const results = [];
const writes = [];
const defaults = path.join(root, 'credentials.json');
const read = p => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } };
const save = (p, v) => fs.writeFileSync(p, JSON.stringify(v));
const fixtureProcess = { pid: 1001, ppid: 1000, env: {}, once() {}, kill(pid, signal) {
  if (signal !== 0) throw Error('fixture forbids signals');
  if (![1001, 2002].includes(pid)) throw Object.assign(Error('not running'), {code:'ESRCH'});
}, execPath:'/fixture/node', argv:[], execArgv:[], stderr:{write(){}}, exit(){throw Error('unexpected exit');} };
const context = vm.createContext({process:fixtureProcess, console, setTimeout, clearTimeout, setInterval, clearInterval, AbortSignal, AbortController, fetch:()=>{throw Error('real fetch forbidden');}, Date, Buffer});
const mod = new vm.SourceTextModule(fs.readFileSync(modulePath, 'utf8'), {context});
const writeCreds = (c,p) => { save(p,c); writes.push({path:p,clientId:c.clientId,orgId:c.orgId}); return p; };
const deps = {
  'release-entry-rjmaqecg.js':{c:()=>({}),J:()=> 'https://fixture.invalid'},
  'release-entry-repea7xz.js':{R:()=>defaults,pe:writeCreds,S:read},
  'release-entry-x219vpy1.js':{nt:['fixture'],D:class extends Error{},GA:x=>x,EA:()=>({challenge:'fixture',verifier:'fixture'}),LA:()=>{throw Error('real browser forbidden');}},
  child_process:{spawn:()=>{throw Error('real process forbidden');},spawnSync:()=>({stdout:'Thu Jan 1 00:00:00 1970'})},
  fs, os:{homedir:()=>root}, path
};
await mod.link(async spec => {
  const values=deps[spec.split('/').at(-1)] ?? deps[spec];
  if (!values) throw Error(`unexpected dependency ${spec}`);
  return new vm.SyntheticModule(Object.keys(values), function(){for(const [k,v] of Object.entries(values))this.setExport(k,v);}, {context});
});
await mod.evaluate();
const api=mod.namespace;
function check(name, condition, classification='verified-control-flow', detail=null) {
  results.push({name,passed:Boolean(condition),classification,detail});
  if(!condition)throw Error(name);
}
const now=Date.now();
const lock=path.join(root,'lock');
check('first-claim-creates-exclusive-lock',api._i(lock,now+60000,()=>now) && read(lock).pid===1001);
check('live-owner-prevents-second-claim',!api._i(lock,now+60000,()=>now));
save(lock,{pid:2002,until:now+60000});api.$t(lock);
check('release-does-not-delete-another-owner-lock',read(lock)?.pid===2002);
save(lock,{pid:777777,until:now+60000});
check('dead-owner-lock-is-reclaimed',api._i(lock,now+60000,()=>now) && read(lock).pid===1001);
save(lock,{pid:2002,until:now-1});
check('expired-lock-is-reclaimed',api._i(lock,now+60000,()=>now));
api.$t(lock);
check('owner-release-removes-lock',!fs.existsSync(lock));

function pending(id){return {apiOrigin:'https://fixture.invalid',clientId:'fixture-client',deviceCode:'fixture-device',pairingId:id,verifier:'fixture-verifier',verificationUrl:'https://fixture.invalid/approve',expiresAt:Date.now()+60000};}
async function run(name,action,status=200,body=null){
  const dir=path.join(root,name);fs.mkdirSync(dir);
  const p=path.join(dir,'pending.json'),cred=path.join(dir,'cred.json');save(p,pending('old-flow'));
  let calls=0;
  const fetchImpl=async url=>{
    if(url.endsWith('/mcp/oauth/device/token')){
      calls++;action?.({p,cred});
      return {ok:status===200,status,json:async()=>body??{access_token:'synthetic-access',refresh_token:'synthetic-refresh',expires_in:60}};
    }
    if(url.endsWith('/v3/self'))return {ok:true,status:200,json:async()=>({org_id:'fixture-old-org'})};
    throw Error(`unexpected HTTP ${url}`);
  };
  let result,error;
  try{result=await api.ys({finish:true,apiOrigin:'https://fixture.invalid',pendingPath:p,path:cred,fetchImpl,now:()=>Date.now(),sleep:async()=>{}});}catch(e){error=e.message;}
  return {result,error,pending:read(p),credentials:read(cred),calls};
}
let r=await run('normal');
check('finisher-saves-result-and-removes-matching-pending',r.result?.state==='signed_in' && !r.pending && r.credentials?.orgId==='fixture-old-org');
r=await run('removed',({p})=>fs.unlinkSync(p));
check('removed-pending-prevents-credential-write',Boolean(r.error) && !r.credentials);
r=await run('new-login',({cred})=>save(cred,{clientId:'other-client',orgId:'other-org'}));
check('changed-client-id-prevents-old-result-write',Boolean(r.error) && r.credentials?.orgId==='other-org');
r=await run('replaced',({p})=>save(p,pending('new-flow')));
check('changed-pairing-id-after-poll-can-still-write-old-result',r.result?.state==='signed_in' && r.credentials?.orgId==='fixture-old-org' && r.pending?.pairingId==='new-flow','observed-file-replacement-gap','HTTP 대기 중 pending 파일을 다른 유효 flow로 교체. 실제 다중 CLI에서 이 교체가 가능한지는 미검증.');
r=await run('denied',null,400,{error:'access_denied'});
check('denied-finisher-keeps-explicit-ended-reason',r.error?.includes('declined') && r.pending?.ended?.includes('declined') && !r.credentials);
r=await run('expired',null,400,{error:'expired_token'});
check('expired-finisher-distinguishes-expiry',r.error?.includes('expired') && r.pending?.ended?.includes('expired') && !r.credentials);
const payload={module_sha256:crypto.createHash('sha256').update(fs.readFileSync(modulePath)).digest('hex'),fixture_root:root,real_http_calls:0,real_credentials_read:0,scope:'수정하지 않은 배포 device-sign-in 모듈. HTTP·자격 저장 helper·프로세스 존재 확인은 fixture. 파일·lock은 격리 폴더에서 실제 처리.',results,passed:results.every(x=>x.passed)};
fs.writeFileSync(output,JSON.stringify(payload,null,2)+'\n');
console.log(JSON.stringify({passed:payload.passed,cases:results.length,output}));
