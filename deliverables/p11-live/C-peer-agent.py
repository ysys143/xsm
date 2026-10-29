"""SSH-stdin control of one owned C fixture; never echo request arguments."""
import importlib.util
import json
import os
from pathlib import Path
import sys


def main():
    os.umask(0o077)
    root=Path(sys.argv[1]).resolve()
    spec=importlib.util.spec_from_file_location('C_fixture_lib',root/'code/C-fixture-lib.py')
    lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
    os.environ['HOME']=str(root/'home');os.environ['PYTHONDONTWRITEBYTECODE']='1'
    native_home='/Users/jaesolshin/.codex-3'
    node=lib.Node(root,'peer',native_home)
    print(json.dumps({'ready':True,'pid':os.getpid(),'root':str(root),'role':'controlled-peer'}),flush=True)
    try:
        for line in sys.stdin:
            request=json.loads(line);op=request.get('op')
            try:
                if op=='start':result={'handle':node.start(),'endpoint':node.endpoint_hash()}
                elif op=='join':result=node.join(request['ticket'])
                elif op=='register':result=node.register()
                elif op=='team':result=node.team()
                elif op=='who':result=node.who()
                elif op=='process':result=node.process(request['phase'],request['body_sha256'])
                elif op=='counts':result={'native_model_calls':len(node.cache)}
                elif op=='cleanup':result=node.cleanup()
                else:raise ValueError('operation outside fixture control')
                reply={'id':request.get('id'),'ok':True,'result':result}
            except Exception as exc:
                reply={'id':request.get('id'),'ok':False,'operation':op,'fixture_operation':getattr(exc,'operation',op),'error':getattr(exc,'detail',lib.safe_error(exc))}
            finally:
                request.clear()
            print(json.dumps(reply),flush=True)
            if op=='cleanup':break
    finally:
        if node.proc and node.proc.poll() is None:node.cleanup()


if __name__=='__main__':main()
