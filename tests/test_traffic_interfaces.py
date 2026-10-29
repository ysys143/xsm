"""Explicit traffic policy on real receive paths; defaults stay observation-only."""
import json
import os
from pathlib import Path
from unittest import mock

from tests.test_xsm import TempState


class TrafficInterfacesTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters,config,paths,registry
        self.a=registry.upsert('codex',self.tmp+'/profile','a',os.getpid(),self.tmp,name='a')
        self.b=registry.upsert('codex',self.tmp+'/profile','b',os.getpid(),self.tmp,name='b')
        self.config,self.paths=config,paths
        paths.write_json(paths.path(config.CONFIG),{'traffic_control':{'mode':'strict','window_seconds':10,'max_same_body':1}})
        patcher=mock.patch.object(adapters,'to_codex',return_value='Queued message q for thread b.')
        self.transport=patcher.start();self.addCleanup(patcher.stop)

    def send(self,**kwargs):
        from xsm import send
        return send.send('codex:b','same payload',sender=self.a,**kwargs)

    def test_strict_defer_retains_original_and_same_id_passive_retry_after_window(self):
        from xsm import abuse,handoff,ledger,receive
        with mock.patch.object(abuse.time,'time',return_value=100):
            first=self.send(wake=False);second=self.send(wake=False)
            pack=receive.take_inbox_claims(self.b)
            self.assertEqual(len(pack['claims']),1)
            deferred=second if pack['claims'][0]['id']==first.msg_id else first
            self.assertTrue(any('Deferred' in m for m in pack['messages']))
            receive.ack_inbox(self.b,[c['token'] for c in pack['claims']])
            self.assertEqual(handoff.status(self.b,deferred.msg_id)['delivery_state'],'held')
            self.assertEqual(handoff.status(self.b,deferred.msg_id)['message']['body'],'same payload')
            self.assertIsNone(ledger.status(deferred.msg_id).get('outcome'))
        with mock.patch.object(abuse.time,'time',return_value=111):
            retry=self.send(wake=False,msg_id=deferred.msg_id,resend=True)
            self.assertEqual(retry.status,'stored')
            pack=receive.take_inbox_claims(self.b)
            self.assertEqual([c['id'] for c in pack['claims']],[deferred.msg_id])
            receive.ack_inbox(self.b,[c['token'] for c in pack['claims']])
            self.assertEqual(handoff.status(self.b,deferred.msg_id)['status'],'acknowledged')

    def test_read_only_reply_polls_do_not_count_as_new_messages(self):
        from xsm import abuse,envelope,handoff,receive
        with mock.patch.object(abuse.time,'time',return_value=100):
            sent=self.send(wake=False)
            parsed=envelope.parse(handoff.status(self.b,sent.msg_id)['message']['content'])
            for _ in range(5):
                self.assertEqual(receive.check(parsed,self.b)[0],'pass')
        history=json.loads(next(Path(self.paths.path('traffic')).glob('*.json')).read_text())
        self.assertEqual(len(history),1)

    def test_native_hook_can_retry_a_deferred_original_without_a_new_permission_question(self):
        from xsm import abuse,handoff,receive
        with mock.patch.object(abuse.time,'time',return_value=100):
            first=self.send();first_wire=self.transport.call_args.args[2]
            second=self.send();second_wire=self.transport.call_args.args[2]
            def deliver(wire):
                with mock.patch.object(receive,'register',return_value=self.b):
                    return receive.handle({'hook_event_name':'UserPromptSubmit','session_id':'b','turn_id':'t','cwd':self.tmp,'prompt':wire})
            deliver(first_wire)
            blocked=deliver(second_wire)
            self.assertEqual(blocked['decision'],'block')
            self.assertIn('traffic rate-limited',blocked['reason'])
            self.assertNotIn('your yes',blocked['reason'])
        with mock.patch.object(abuse.time,'time',return_value=111):
            retry=self.send(msg_id=second.msg_id,resend=True)
            self.assertEqual(retry.msg_id,second.msg_id)
            allowed=deliver(self.transport.call_args.args[2])
            self.assertNotEqual((allowed or {}).get('decision'),'block',allowed)
            self.assertEqual(handoff.status(self.b,second.msg_id)['status'],'handoff-recorded')
