from pathlib import Path
import ast,json,time,subprocess,hashlib,os,signal
r=Path(__file__).resolve().parent
original=r/'run.py';tree=ast.parse(original.read_text());nodes=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.Assign,ast.FunctionDef))];ns={'__file__':str(original),'__name__':'factory_followup_definitions'};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(original),'exec'),ns)
d=json.loads((r/'result.json').read_text());ns['out']=d;ns['actors']=[]
def save(name,value):
 target=r/('verified-'+name);target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
ns['save']=save
old=next(x for x in d['actual_registration_setup'] if x['role']=='receiver-initial');assert ns['start'](old['native_pid'])!=old['native_lstart']
folder=r/'receiver-resume-verified';folder.mkdir(mode=0o700)
a=ns['launch']('receiver-resume-verified',ns['RESUME_GOAL'],d['receiver_native_cid'])
end=min(time.time()+140,ns['DEADLINE']-25)
while time.time()<end and a['proc'].poll() is None:
 ns['register_actual'](a);time.sleep(.1)
if a['proc'].poll() is None:
 ns['kill_exact'](a['proc'].pid,a['entry']['lstart'],'own bounded verified resume CLI');a['proc'].wait(timeout=5)
a['entry']['exit_code']=a['proc'].poll();a['entry']['observed_cid']=ns['cid'](a)
save('followup.json',{'invocation':a['entry'],'same_CID':a['entry']['observed_cid']==d['receiver_native_cid'],'registrations':d.get('actual_registration_setup',[]),'original_request_id':d['fault']['claims'][0]['id'],'original_after':ns['read'](d['original_file'])})
for stream in a['streams']:stream.close()
print(json.dumps({'verified_resume_exit':a['proc'].returncode,'same_CID':a['entry']['observed_cid']==d['receiver_native_cid'],'root':str(r)}),flush=True)
