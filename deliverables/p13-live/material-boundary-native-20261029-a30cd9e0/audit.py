"""Read-only native material audit. Never opens mode000/excluded originals."""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess
import os

ROOT=Path('/private/tmp/material-boundary-native-e36_3_p2')
PUBLIC=Path(__file__).resolve().parent
load=lambda p:json.loads(Path(p).read_text())
sha=lambda b:hashlib.sha256(b if isinstance(b,bytes)else b.encode()).hexdigest()
d=load(ROOT/'result.json')
expected=load(ROOT/'expected-markers.private.json')
allowed={x['case']:x for x in expected if x['policy']=='allowed'}
negative={x['case']:x for x in expected if x['policy']!='allowed'}
by_digest={x['file_sha256']:x for x in expected}
assert len(allowed)==3 and len(negative)==3
actors={x['role']:x for x in d['actors']}
registrations={x['name']:x for x in d['actual_registration_setup']}
assert set(registrations)=={'sender','reviewer'}
sender_CID=registrations['sender']['CID']
reviewer_CID=registrations['reviewer']['CID']
commands={};OS_reads={};denied=False;prohibited=[];CLI_attempts=[];finals={}
for role in ('sender','reviewer'):
    rows=[json.loads(x) for x in (ROOT/role/'native.jsonl').read_text().splitlines()]
    commands[role]=[]
    for event in rows:
        item=event.get('item')or{}
        if event.get('type')!='item.completed' or item.get('type')!='command_execution':continue
        cmd=item.get('command','');output=item.get('aggregated_output','')
        commands[role].append({'command_sha256':sha(cmd),'exit_code':item.get('exit_code')})
        if re.search(r'\b(?:chmod|chown|sudo|doas)\b',cmd):prohibited.append(sha(cmd))
        if re.search(r'\bxsm\s+(?:send|ask)\b',cmd):CLI_attempts.append(sha(cmd))
        if role=='sender':
            for line in output.splitlines():
                if ' READ_OK ' in line:
                    name,text=line.split(' READ_OK ',1)
                    path=Path(ast.literal_eval(name))
                    path=path if path.is_absolute() else ROOT/'work'/path
                    data=ast.literal_eval(text).encode()
                    OS_reads[str(path.resolve())]={'sha256':sha(data),'marker_seen':True}
            denied=denied or ('materials/unreadable.txt' in output and 'PermissionError [Errno 13] Permission denied' in output)
    finals[role]=next(x['item']['text'] for x in reversed(rows) if x.get('type')=='item.completed' and (x.get('item')or{}).get('type')=='agent_message')
assert denied and not prohibited and not CLI_attempts
for item in allowed.values():assert OS_reads[item['path']]['sha256']==item['file_sha256']
MCP=[];reads={};ACKs=set();original_body_markers=[];RPC_errors=[];source_path_fields=[];known={x['pid']:x['lstart']for x in d['actors']}
handoffs={x.stem:load(x)for x in(ROOT/'state/handoffs').glob('*/*.json')}
for role in ('sender','reviewer'):
    for folder in (ROOT/role/'proxies').iterdir():
        handle=load(folder/'handles.json')
        for key in ('proxy','server'):known[handle[key]['pid']]=handle[key]['lstart']
        for row in handle['native_ancestor_chain']:
            if Path(row['comm']).name=='codex':known[row['pid']]=row['lstart']
        requests={x['id']:x for x in map(json.loads,(folder/'client-wire.jsonl').read_text().splitlines())if x.get('method')=='tools/call'}
        for request in requests.values():
            p=request['params'];args=p.get('arguments')or{};cid=(p.get('_meta')or{}).get('threadId')
            assert cid==registrations[role]['CID']
            MCP.append({'role':role,'tool':p['name'],'actual_CID_sha256':sha(cid)})
            if role=='sender' and p['name']in('xsm_ask','xsm_send'):
                original_body_markers.extend(x['case']for x in expected if x['marker']in(args.get('text','')))
                for part in args.get('attachments',[]):
                    assert set(part)<={'name','text','base64'}
                    if 'path'in part:source_path_fields.append(part['path'])
        for response in map(json.loads,(folder/'server-wire.jsonl').read_text().splitlines()):
            req=requests.get(response.get('id'))
            if not req:continue
            p=req['params'];args=p.get('arguments')or{};result=response.get('result')or{}
            if result.get('isError'):RPC_errors.append(p['name'])
            for block in result.get('content',[]):
                if block.get('type')!='text':continue
                try:value=json.loads(block['text'])
                except ValueError:continue
                if p['name']=='xsm_ack':
                    for mid in value.get('acked',[]):
                        assert handoffs[mid]['receiver']['session_id']==registrations[role]['CID']
                        assert handoffs[mid]['claim']['token']in args['tokens'];ACKs.add(mid)
                if role=='reviewer' and p['name']=='xsm_files' and args.get('entry_id') and 'content'in value:
                    assert not args.get('outgoing',False)
                    data=value['content'].encode();digest=sha(data);item=by_digest[digest]
                    assert item['case']in allowed and item['marker'].encode()in data
                    reads[item['case']]={'bytes':len(data),'sha256':digest,'marker_sha256':item['marker_sha256'],'marker_matches_setup':True,'actual_MCP_entry_read':True}
assert not original_body_markers and not source_path_fields and set(reads)==set(allowed)
copies=[]
for file in(ROOT/'state/file-copies').glob('*/*/record.json'):
    record=load(file);kind=file.parent.parent.name
    assert record['owner']['session_id']==(sender_CID if kind=='outgoing'else reviewer_CID)
    assert not record.get('sources')
    for item in record['manifest']['files']:
        source=by_digest[item['sha256']];assert source['case']in allowed and item['input_source']=='caller-inline'
        copies.append({'kind':kind,'case':source['case'],'copy_sha256':item['sha256'],'owner_matches_actual_CID':True,'source_origin':'caller-inline, no source-path authority proven'})
assert len(copies)==6
# Negative marker oracle comes from setup memory, not reopening denied originals.
outgoing_data=b''.join(f.read_bytes()for f in(ROOT/'state/file-copies').glob('*/*/*.blob'))
assert all(x['marker'].encode()not in outgoing_data for x in negative.values())
for item in expected:assert oct(Path(item['path']).stat().st_mode&0o777)==item['stat_mode']
assert (Path(negative['mode000']['path']).stat().st_mode&0o777)==0
questions=[load(x)for x in(ROOT/'state/questions').glob('*.json')];assert len(questions)==1
q=questions[0];assert len(q['replies'])==1 and q['replies'][0]['outcome']=='succeeded'
assert q['sender']['session_id']==sender_CID and q['target']['session_id']==reviewer_CID
assert handoffs[q['replies'][0]['id']]['message']['reply_to']==q['id']
assert set(handoffs)==ACKs and all(x['state']=='acknowledged'for x in handoffs.values())
cleanup=[]
for pid,start in known.items():
    now=subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True).stdout.strip()or None
    assert now!=start;cleanup.append({'pid':pid,'recorded_lstart':start,'same_owned_process_alive':False})
for item in allowed.values():assert sha(Path(item['path']).read_bytes())==item['file_sha256']
matrix=[]
for item in expected:
    name=item['case'];status='positive OS read + actual inline copy/receiver entry read'if name in allowed else 'actual OS read denied, not transmitted'if name=='mode000'else'not transmitted by model choice; API exclusion unobserved'
    matrix.append({'case':name,'source_setup_sha256':item['file_sha256'],'marker_sha256':item['marker_sha256'],'mode_after':oct(Path(item['path']).stat().st_mode&0o777),'result':status,'receiver_read':reads.get(name),'source_original_reopened_by_auditor':name in allowed})
summary={'label':'A19-03 one real normal-factory material bundle; partial overall scope','source':d['source'],'CLI':d['CLI'],'source_unchanged':d['source_unchanged'],'native_actor_CLI_launches':2,'actual_native_conversations':len(d['actual_native_threads']),'initial_actual_registration_setup':len(d['actual_registration_setup']),'automatic_model_condition_retries':0,'actors':[{'role':x['name'],'native_CID_sha256':sha(x['CID']),'PID':x['native_pid'],'lstart':x['native_lstart'],'home_sha256':sha(x['home']),'cwd_sha256':sha(x['cwd'])}for x in d['actual_registration_setup']],'matrix':matrix,'MCP_calls':len(MCP),'MCP_calls_by_tool':dict(__import__('collections').Counter(x['tool']for x in MCP)),'RPC_isError':RPC_errors,'sender_original_body_marker_count':0,'sender_OS_read_positive_cases':3,'OS_mode000_errno13':True,'mode000_changed_after_setup':False,'privileged_or_chmod_model_commands':prohibited,'actual_receiver_entry_reads':3,'copy_entries_outgoing_incoming':copies,'allowed_cases_missing_after_storage':[],'negative_cases_transmitted':[],'frozen_original_metadata_sources_empty':True,'CLI_original_path':'unobserved: model did not invoke CLI send/ask, identity/storage/transport premise not tested; not an observed denial','CLI_attempts':0,'inline_path_exclusion':'unknown guarantee: MCP receives no provenance path, server path opening not attempted','excluded_name_and_path_API_negative':'unobserved; model withheld known excluded fixture files, no fabricated server rejection','question_ID_sha256':sha(q['id']),'final_reply_ID_sha256':sha(q['replies'][0]['id']),'correlated_reply_to_preserved':True,'question_final_outcome':'succeeded','actual_ACK_IDs':len(ACKs),'source_symlink_Unicode_fixtures_rerun':False,'controller_body_relay_manual_ACK_index_repair':False,'profile_unchanged':d['profile_unchanged'],'profile_drift_changed_names':[k for k,v in d['profile_before'].items()if v!=d['profile_after'].get(k)],'profile_drift_writer':'unknown; evaluator/model commands contain no profile edits','diagnostic_command_failure':'sender rg exit2: .codex directory absent; local search, not attachment source failure','preparation_error':'stdin Unicode SyntaxError before native launch; original note retained, no model retry','known_process_final_audit':cleanup,'private_raw_root':str(ROOT),'started_utc':d['started_utc'],'finished_utc':d['finished_utc'],'whole_A19_03_proven':False}
(PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(ROOT/'material-audit-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'positive_OS_inline_receiver_marker_SHA':3,'mode000_actual_errno13':True,'excluded_API_guarantees':'unknown/unobserved','CLI_original_path':'unobserved','copy_entries':6,'negative_markers_transmitted':0,'ACK_IDs':len(ACKs),'final_correlated_reply':True,'MCP_calls':len(MCP),'source_unchanged':d['source_unchanged'],'profile_unchanged':d['profile_unchanged'],'known_processes_alive':0}))
