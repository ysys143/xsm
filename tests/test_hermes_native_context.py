"""Two-phase native context handoff against real isolated protocol storage."""
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'clients/python'))
from xsm_client import XsmClient
from xsm_host import XsmHost,render_inbox_packet
spec=importlib.util.spec_from_file_location('hermes_context_binding',ROOT/'integrations/hermes/xsm.py')
module=importlib.util.module_from_spec(spec)
mutation=os.environ.get('XSM_HERMES_CONTEXT_MUTANT')
if mutation:
    code=Path(spec.origin).read_text()
    before,after=("state['turn'] != turn_id",'False') if mutation=='ignore-turn' else ('        if not observed:\n','        if False:\n')
    changed=code.replace(before,after,1)
    if changed==code:raise RuntimeError('native context guard moved; update deliberate mutation')
    exec(compile(changed,spec.origin,'exec'),module.__dict__)
else:
    spec.loader.exec_module(module)


class HermesNativeContextTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='xsm-hermes-context-')
        self.env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ}
        self.env.update(HOME=self.temp.name,XSM_HOME=self.temp.name+'/state',PYTHONPATH=str(ROOT))
        self.command=[sys.executable,'-B','-m','xsm','protocol','serve','--stdio']
        self.context=module.NativeContext(render_inbox_packet)
        async def deliver(packet,options):return await self.context.deliver('native-sid',self.host,packet,options)
        self.host=await XsmHost.open(runtime='hermes-context-test',profile='isolated',conversation='native-sid',
            cwd=str(ROOT),command=self.command,env=self.env,deliver=deliver,automatic_delivery=False)
        self.sender=await XsmClient.connect(self.command,cwd=str(ROOT),env=self.env)
        self.origin=await self.sender.session_open(runtime='context-sender',profile='isolated',conversation='sender',cwd=str(ROOT))

    async def asyncTearDown(self):
        await self.context.close_host('native-sid',self.host)
        await self.host.close();await self.sender.close();self.temp.cleanup()

    async def send(self):
        await self.sender.operation_call(self.origin['session'],'xsm_send',{'target':'ref:'+self.host.session['ref'],
            'text':'quiet original for exact native context','wake':'never','request_id':'context-original'})

    async def current(self):
        return await self.host.call('xsm_inbox',{'message_ids':['context-original']})

    async def test_exact_native_user_context_observation_is_required_before_admission(self):
        await self.send();text=await self.context.begin('native-sid',self.host,'turn-1')
        self.assertIn('quiet original for exact native context',text)
        self.assertIn('After reading, call xsm_ack',text)
        before=await self.current();token=before['claims'][0]['token']
        for sid,host,turn,api,messages in (
            ('wrong',self.host,'turn-1','api-1',[{'role':'user','content':text}]),
            ('native-sid',object(),'turn-1','api-1',[{'role':'user','content':text}]),
            ('native-sid',self.host,'other-turn','api-1',[{'role':'user','content':text}]),
            ('native-sid',self.host,'turn-1','',[{'role':'user','content':text}]),
            ('native-sid',self.host,'turn-1','api-1',[{'role':'assistant','content':text}]),
            ('native-sid',self.host,'turn-1','api-1',[{'role':'user','content':text[:30]}])):
            self.assertFalse(await self.context.observe(sid,host,turn,api,messages))
        self.assertFalse(self.context.pending[('native-sid',id(self.host))]['task'].done())
        self.assertTrue(await self.context.observe('native-sid',self.host,'turn-1','api-1',
            [{'role':'user','content':[{'type':'input_text','text':'natural input\n'+text}]}]))
        current=await self.current();self.assertEqual(current['claims'][0]['token'],token)
        ack=await self.host.call('xsm_ack',{'tokens':[token]});self.assertEqual(ack['acked'],['context-original'])
        self.assertFalse(await self.context.observe('native-sid',self.host,'turn-1','api-1',[{'role':'user','content':text}]))

    async def test_end_without_native_observation_releases_original_without_ack(self):
        await self.send();text=await self.context.begin('native-sid',self.host,'turn-1')
        token=(await self.current())['claims'][0]['token']
        await self.context.close_host('native-sid',self.host)
        fresh=await self.current();self.assertNotEqual(fresh['claims'][0]['token'],token)
        self.assertIn('quiet original',fresh['messages'][0])
        self.assertFalse(await self.context.observe('native-sid',self.host,'turn-1','api-1',[{'role':'user','content':text}]))

    async def test_close_waits_for_inflight_inbox_response_and_releases_its_exact_claim(self):
        await self.send();original=self.host.client.operation_call;read=asyncio.Event();release=asyncio.Event();seen=[]
        async def invoke(session,operation,args):
            value=await original(session,operation,args)
            if operation=='xsm_inbox' and not seen:
                seen.extend(value['claims']);read.set();await release.wait()
            return value
        self.host.client.operation_call=invoke
        beginning=asyncio.create_task(self.context.begin('native-sid',self.host,'turn-1'))
        await asyncio.wait_for(read.wait(),3)
        closing=asyncio.create_task(self.context.close_host('native-sid',self.host));await asyncio.sleep(0)
        release.set();await closing
        with self.assertRaisesRegex(RuntimeError,'not open'):await beginning
        fresh=await self.current();self.assertNotEqual(fresh['claims'][0]['token'],seen[0]['token'])

    async def test_empty_boundary_and_missing_turn_do_not_create_a_handoff(self):
        self.assertEqual(await self.context.begin('native-sid',self.host,'empty-turn'),'')
        self.assertEqual(self.context.pending,{})
        await self.send()
        with self.assertRaisesRegex(RuntimeError,'turn identity'):await self.context.begin('native-sid',self.host,'')
        packet=await self.current();self.assertEqual([c['id'] for c in packet['claims']],['context-original'])
