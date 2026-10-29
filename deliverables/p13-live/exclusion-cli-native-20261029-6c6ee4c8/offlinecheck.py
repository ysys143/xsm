"""Evidence check only: never read protected LICENSE/negative source originals."""
from pathlib import Path
import json,hashlib
ROOT=Path('/private/tmp/exclusion-cli-native-jhehrztq')
PUBLIC=Path(__file__).resolve().parent
def load(p):return json.loads(Path(p).read_text())
def main():
 a=load(ROOT/'A17.private.json');b=load(ROOT/'A19.private.json');originals=load(ROOT/'originals.private.json')
 assert a['same_realpath']and a['pointer_bytes_unchanged']
 assert a['exclusion_status']=={'canonical':'excluded','alias':'excluded'}
 regs=[x for x in a['trace']if x['kind']=='direct registry.upsert API'];assert len(regs)==2 and all(x['excluded']and x['registered']is False for x in regs)
 discover=next(x['result']for x in a['trace']if x['kind']=='direct directory.discover API')
 assert discover['candidates']==[]and discover['status']=='unknown'and discover['reason']=='caller_or_policy_unverified'
 assert [x['code']for x in a['trace']if x['kind']=='direct files.prepare_cli API']==['excluded-or-unknown']*2
 assert [x['code']for x in b['trace']if x['kind']=='direct files.prepare_cli API']==['excluded-or-unknown','credential-path']
 parsed=[x for x in b['trace']if x['kind'].startswith('actual cli.main')]
 assert len(parsed)==2
 for x,code in zip(parsed,['excluded-or-unknown','credential-path']):
  assert x['exit_code']==2 and x['response']['code']==code and x['response']['body_sent']is False
  assert x['natural_identity_context']['basis']=='thread_id'and x['natural_identity_context']['sure']is True
 for d in [a,b]:
  assert not d['protected_content_open_events']and not any(d['counts_after'].values())
  assert d['sandbox_markers_before']==d['sandbox_markers_after']=={'CODEX_SANDBOX':False,'XSM_SANDBOXED':False}
  for key,item in originals.items():assert d['original_stat_after'][key]==item['setup_stat']
 proof=load(ROOT/'source-proof.json');assert proof['frozen315_matches']
 summary={'verdict':'pass for these local current-caller exclusion cells; no whole-criterion/plan completion claim','A17_05':{'same_native_cwd_realpath':True,'symlink_alias_only':True,'registry_upsert_both_rejected':True,'preexisting_self_pointer_bytes_preserved':True,'discovery':discover,'CLI_capture_API_rejections':['excluded-or-unknown']*2,'in_process_CLI_parser_executed':False},
 'A19_03':{'direct_files_prepare_cli_codes':['excluded-or-unknown','credential-path'],'real_cli_main_parser':[{ 'label':x['label'],'exit_code':x['exit_code'],'code':x['response']['code'],'status':x['response']['status'],'body_sent':False,'manifest_id':None,'natural_identity_context':x['natural_identity_context']}for x in parsed],'parser_scope':'real cli.main argv parser/handler/capture path in current Python workers; not an OS python -m CLI subprocess'},
 'native_identity':'actual current CID/home/cwd verified in native DB and rollout header, actual OS Codex ancestor PID/lstart; no caller certainty assignment','sandbox_markers_cleared_or_added':False,'direct_API_argument_scope':'factual registered native record; direct API does not independently establish MCP caller certainty','protected_source_open_events':0,'protected_original_postread_or_posthash':0,'originals':{k:{'setup_sha256':v['setup_sha256'],'stat_preserved':True,'post_run_hash':'not read'}for k,v in originals.items()},'counts_each_state':{'ledger':0,'canonical':0,'copy_records':0,'copy_blobs':0,'body_sent':0},'private_registry_self_records_per_state':[a['registry_records'],b['registry_records']],'new_models':0,'new_native_TUIs':0,'source_frozen315_unchanged':True,'preexisting_current_primary_difference':proof['current_primary_mismatches'],'source_used':'/private/tmp/xsm-doctor-privacy-frozen-47o6orah','private_raw_root':str(ROOT),'limits':['A17 excluded caller discovery is unknown/hidden, not an ordinary successful listing','A17 uses direct APIs, A19 also uses actual in-process CLI parser','known sensitive name and configured exclusion do not prove all unknown secrets or inline source-path policy','prior native hidden/outside/mode000 and fixture symlink/Unicode cases reused only']}
 (PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'A17':'pass API trace','A19':'pass API and real cli.main parser','source_opens':0,'postread':0,'copies':0,'body_sent':0,'ledger':0,'new_models':0}))
if __name__=='__main__':main()
