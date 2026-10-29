import importlib.util,json,os,socket,time
from pathlib import Path
root=Path(__file__).parent
spec=importlib.util.spec_from_file_location('carrier_fault_helper',root/'run.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
profile='(version 1)(allow default)(deny network-outbound(remote tcp "*:*"))(deny network-outbound(remote udp "*:*"))(allow network-outbound(remote udp "localhost:*"))'
held=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);held.bind(('0.0.0.0',0));port=held.getsockname()[1]
os.environ['CARRIER_HELD_PORT']=str(port)
result={'kind':'same-host product services with native-process IPv6 socket fault','profile':profile,
        'host_baseline':json.loads((root/'host-baseline.json').read_text()),'requested_port_held_by_controller':port,
        'started_at':time.time(),'native_key_or_ticket_values_read':False,'global_ipv6_or_firewall_changed':False}
nodes=[]
try:
    for role in ('a','b'):nodes.append(r.Node('ipv6-fault',role,profile,launcher=root/'observe-v6.py'))
    for node in nodes:node.ready()
    result['initial_status']=[{'service_pid':n.proc.pid,'engine_pid':n.engine_pid,'endpoint_id':n.info['endpoint_id'],
        'bound_addresses':n.info['transport']['bound_addresses'],'requested_port':n.info['transport']['requested_port'],
        'port_fallback':n.info['transport']['port_fallback'],'relay_mode':n.info['transport']['relay_mode']}for n in nodes]
    a,b=nodes
    a.cli('init','ipv6-socket-fault','--machine-name','ipv6-fault-a')
    ticket=a.cli('invite','--once','--expires','120')
    b.cli('join','--ticket-file',ticket['ticket_file'],'--machine-name','ipv6-fault-b')
    for node in nodes:node.info=node.rpc({'op':'status'},3)
    result['both_active']=all(n.info.get('active')for n in nodes)
    result['roundtrips']=[r.ping(a,b),r.ping(b,a)]
    result['socket_fault_observations']=[]
    for node in nodes:
        events=[json.loads(line)for line in Path(str(node.trace)+'.sockets.jsonl').read_text().splitlines()]
        result['socket_fault_observations'].append({'engine_pid':node.engine_pid,
          'loaded_in_engine':any(e['event']=='interpose-loaded'and e['pid']==node.engine_pid for e in events),
          'ipv6_denied_count':sum(e['event']=='ipv6-socket-denied'and e['pid']==node.engine_pid and e['errno']==47 for e in events),
          'ipv4_socket_success_count':sum(e['event']=='socket-passed'and e['pid']==node.engine_pid and e['family']==2 and e['errno']==0 for e in events),
          'recorded_process_ids':sorted({e['pid']for e in events})})
    result['passed']=result['both_active'] and all(n['port_fallback']and n['requested_port']==port and all(not addr.startswith('[')and int(addr.rsplit(':',1)[1])!=port for addr in n['bound_addresses'])for n in result['initial_status']) \
        and all(e['loaded_in_engine']and e['ipv6_denied_count']>0 and e['ipv4_socket_success_count']>0 for e in result['socket_fault_observations']) \
        and all(e['path']=='direct'and e['tls_origin_matches']and e['request_digest_matches']and e['response_digest_matches']for e in result['roundtrips'])
except Exception as error:
    result['passed']=False;result['failure_code']=getattr(error,'code',type(error).__name__)
finally:
    result['cleanup']=[node.close()for node in nodes]
    held.close()
    result['udp_rebind_after_cleanup']=[]
    addresses=[addr for n in result.get('initial_status',[])for addr in n['bound_addresses']]+['0.0.0.0:'+str(port)]
    for address in addresses:
        test=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:test.bind(('0.0.0.0',int(address.rsplit(':',1)[1])));result['udp_rebind_after_cleanup'].append({'address':address,'free':True})
        except OSError as error:result['udp_rebind_after_cleanup'].append({'address':address,'free':False,'errno':error.errno})
        finally:test.close()
    result['finished_at']=time.time();r.save(r.REPORT/'result.json',result)
print(json.dumps(result,ensure_ascii=False))
