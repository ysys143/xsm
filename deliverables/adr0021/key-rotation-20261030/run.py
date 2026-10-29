from pathlib import Path
import datetime, hashlib, json, os, sys
frozen=Path('/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr21-final-20261030-fx0yt4x3').resolve()
sys.path.insert(0,str(frozen))
os.environ['XSM_NET_BINARY']=str(frozen/'native/xsm-net/target/release/xsm-net')
from tests.test_network_service import NativeNetworkServiceTests, process_table
output=Path(__file__).resolve().parent
case=NativeNetworkServiceTests('test_public_cli_reusable_join_retry_and_third_device')
record={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_manifest_sha256':hashlib.sha256((frozen/'manifest.json').read_bytes()).hexdigest(),'kind':'same-host real public CLI and Rust QUIC; no model sessions','completed':False}
pids=[]
try:
 case.setUp()
 team=case.initialize(case.a)
 ticket,_=case.invite(case.a)
 case.join(case.b,ticket)
 old=case.b.identity
 case.ping(case.b,case.a)
 replacement=case.node('replacement-device')
 new=replacement.identity
 assert old!=new
 fresh,_=case.invite(case.a,once=True)
 case.join(replacement,fresh)
 case.ping(replacement,case.a)
 case.ping(case.a,replacement)
 case.a.cli('remove',old)
 assert case.members(case.a)[old]=='removed'
 assert case.members(case.a)[new]=='active'
 rejected=case.ping(case.b,case.a,success=False)
 assert rejected.get('code')=='peer-refused', rejected
 case.ping(replacement,case.a)
 case.ping(case.a,replacement)
 assert case.b.identity==old
 pids=[n.process.pid for n in (case.a,case.b,replacement)]+[n.sidecar_pid for n in (case.a,case.b,replacement)]
 record.update(network_id=team,old_public_key=old,replacement_public_key=new,old_removed=True,new_active=True,old_transport_rejection=rejected['code'],new_bidirectional_ping=True,old_identity_not_overwritten=True,completed=True)
finally:
 case.doCleanups()
 table=process_table()
 remaining=[pid for pid in pids if pid in table]
 record.update(owned_pids=pids,owned_pids_remaining=remaining,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 (output/'results.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
 assert not remaining
print(json.dumps({k:v for k,v in record.items() if k not in ('network_id','old_public_key','replacement_public_key')}))
