import hashlib,json,os,sys,threading,time
from pathlib import Path
from xsm import config,directory,identity,network,network_directory,network_messages,network_transport,paths,registry
lock=threading.Lock();counts={};actors={}
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
def note(x):
    x.update(at=time.time(),service_pid=os.getpid())
    with lock,Path(os.environ['POLICY_TRACE']).open('a')as out:out.write(json.dumps(x)+'\n')
native=directory._native
def observed_native(record,endpoint):
    sid=record['session_id'];counts[sid]=counts.get(sid,0)+1
    return native(record,endpoint)
directory._native=observed_native
call=network_transport.Sidecar.call
def observed_call(self,op,timeout=30,**kwargs):
    result=call(self,op,timeout=timeout,**kwargs)
    body=kwargs.get('body')
    if op=='request'and isinstance(body,dict)and body.get('op')in('ping','directory','deliver'):
        note({'event':'request-response','operation':body['op'],'request_sha256':digest(body),
              'response_sha256':digest(result.get('body')),'tls_origin':result.get('origin'),
              'expected_peer':kwargs['peer']['id'],'transport':result.get('transport'),'native_event_id':result.get('id')})
    return result
network_transport.Sidecar.call=observed_call
incoming=network.Daemon.incoming
def observed_incoming(self,origin,request):
    result=incoming(self,origin,request)
    if isinstance(request,dict)and request.get('op')in('ping','directory','deliver'):
        note({'event':'incoming-response','operation':request['op'],'request_sha256':digest(request),
              'response_sha256':digest(result),'tls_origin':origin,'ok':result.get('ok'),'code':result.get('code')})
    return result
network.Daemon.incoming=observed_incoming
local=network.Daemon.local
def operator(self,request):
    op=request.get('op')
    if op=='evaluation-raw':return self.transport.request(request['peer'],request['body'],timeout=8)
    if op=='evaluation-state':
        store=self.store();return {'network_id':store.network_id if store else None,'state_sha256':digest(store.snapshot())if store else None,
            'active_pointer_sha256':hashlib.sha256((network.root()/'active.json').read_bytes()).hexdigest()if store else None,
            'active':bool(store and store.is_active(self.transport.endpoint_id)),
            'members':store.members()if store else [],'native_reads':dict(counts),'actors':actors}
    if op=='evaluation-files':
        import sqlite3,subprocess
        from contextlib import closing
        root=Path(paths.HOME).parent/'file-fixtures';root.mkdir(mode=0o700,exist_ok=True)
        labels=request['labels']
        for label in labels:
            home=root/(label+'-native');home.mkdir(mode=0o700,exist_ok=True)
            work=root/(label+'-work');work.mkdir(mode=0o700,exist_ok=True)
            subprocess.run(['git','init','-q','-b','main',str(work)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=4)
            sid='file-'+label
            row={'runtime':'codex','home':str(home),'cwd':str(work),'session_id':sid,'pid':os.getpid(),'lstart':identity.lstart(os.getpid()),
                 'app_server':False,'ref':'fixture-'+label,'name':'FILE actor '+label,'updated':time.time()}
            rollout=home/(sid+'.jsonl')
            rollout.write_text(json.dumps({'type':'session_meta','payload':{'id':sid},'timestamp':time.time()})+'\n'+json.dumps({'type':'response_item','timestamp':time.time(),'payload':{'type':'function_call','name':'update_plan','arguments':json.dumps({'plan':[{'step':'FILE policy fixture '+label,'status':'in_progress'}]})}})+'\n')
            with closing(sqlite3.connect(home/'state_5.sqlite'))as db,db:
                db.execute('create table if not exists threads(id text primary key,name text,rollout_path text)')
                db.execute('insert or replace into threads values(?,?,?)',(sid,'FILE actor '+label,str(rollout)))
            config.add_home(str(home),'codex');paths.write_json(registry._record_path('codex',sid),row)
            if label in('published','excluded'):directory.publish(row,user_source='operator FILE fixture publication; no actual model')
            actors[label]=row
        if 'excluded'in actors:paths.write_json(paths.path(config.CONFIG),{'directory_excluded_paths':[actors['excluded']['cwd']]})
        return {'actors':actors,'public':{name:network_directory.public_endpoint(row,self.transport.endpoint_id)for name,row in actors.items()},'kind':'FILE actors, not actual LLMs'}
    if op=='evaluation-packet':
        return self.gateway().prepare(actors[request['actor']],request['target'],request['body'],request_id=request['id'],kind='task',wake=False)
    if op=='evaluation-canonical':
        from xsm import handoff
        return {'status':handoff.status(actors[request['actor']],request['id'])['status']}
    return local(self,request)
network.Daemon.local=operator
raise SystemExit(network.main(['serve']))
