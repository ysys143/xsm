"""Private descriptor binding and strict control frames; no model or native SDK."""
import json
import os
import socket
import threading
import unittest
from unittest import mock
from xsm.native_worker_control import WorkerControl, WorkerControlClient, ControlError


class NativeWorkerControlTest(unittest.TestCase):
    def test_cancellation_query_and_stop_report_require_the_bound_pending_request(self):
        state = {'requested': False}; stops = []
        control = WorkerControl(lambda sid: None, cancellation=lambda: state['requested'], stopped=stops.append)
        client = WorkerControlClient(os.dup(control.child.fileno())); control.start()
        try:
            with self.assertRaises(ControlError): client.cancellation_requested()
            client.bind('owned-native')
            self.assertFalse(client.cancellation_requested())
            with self.assertRaises(ControlError): client.report_stopped()
            self.assertEqual(stops, [])
            state['requested'] = True
            self.assertTrue(client.cancellation_requested())
            with self.assertRaises(ControlError):
                client._rpc('native.cancelled', {'native_session_id': 'different'}, 'recorded')
            client.report_stopped()
            self.assertEqual(stops, ['owned-native'])
        finally: client.close(); control.close()

    def test_non_boolean_cancellation_state_is_not_a_positive_request(self):
        control = WorkerControl(lambda sid: None, cancellation=lambda: 1)
        client = WorkerControlClient(os.dup(control.child.fileno())); control.start()
        try:
            client.bind('owned-native')
            with self.assertRaises(ControlError): client.cancellation_requested()
        finally: client.close(); control.close()

    def test_only_bound_native_identity_is_confirmed_and_channel_is_closed(self):
        calls=[]
        control=WorkerControl(calls.append)
        client=WorkerControlClient(os.dup(control.child.fileno()))
        control.start()
        try:
            client.bind('opaque-native')
            self.assertEqual(calls,['opaque-native'])
            self.assertEqual(control.native_id,'opaque-native')
            self.assertFalse(client.socket.get_inheritable())
        finally:client.close();control.close()
        self.assertFalse(control.thread.is_alive())

    def test_refused_binding_never_becomes_admission(self):
        def refuse(native_id):raise ValueError('fixture refusal')
        control=WorkerControl(refuse);client=WorkerControlClient(os.dup(control.child.fileno()));control.start()
        try:
            with self.assertRaises(ControlError):client.bind('not-owned')
            self.assertIsNone(control.native_id)
        finally:client.close();control.close()

    def test_wrong_method_or_authority_fields_do_not_reach_the_binder(self):
        calls=[];control=WorkerControl(calls.append);peer=socket.socket(fileno=os.dup(control.child.fileno()));control.start()
        try:
            with peer.makefile('rwb',buffering=0) as stream:
                for method,params in [('decision.response',{'answer':'allow'}),
                                      ('native.bind',{'native_session_id':'x','owner':'someone-else'})]:
                    stream.write((json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params})+'\n').encode())
                    reply=json.loads(stream.readline())
                    self.assertIn('error',reply)
            self.assertEqual(calls,[])
        finally:peer.close();control.close()

    def test_boolean_request_ids_and_false_positive_confirmation_are_refused(self):
        for ident,bound in [(True,True),(1,1),(1,False)]:
            with self.subTest(ident=ident,bound=bound):
                parent,child=socket.socketpair();client=WorkerControlClient(child.detach())
                def reply():
                    with parent.makefile('rwb',buffering=0) as stream:
                        stream.readline();stream.write((json.dumps({'jsonrpc':'2.0','id':ident,'result':{'bound':bound}})+'\n').encode())
                thread=threading.Thread(target=reply);thread.start()
                try:
                    with self.assertRaises(ControlError):client.bind('native')
                finally:client.close();thread.join(timeout=2);parent.close()

    def test_malformed_request_closes_the_channel_instead_of_hanging_the_frontend(self):
        for wire in (b'{"jsonrpc":"2.0","id":true}\n', b'not-json\n'):
            with self.subTest(wire=wire):
                calls=[];control=WorkerControl(calls.append)
                peer=socket.socket(fileno=os.dup(control.child.fileno()));peer.settimeout(1);control.start()
                try:
                    peer.sendall(wire)
                    self.assertEqual(peer.recv(1),b'')
                    self.assertEqual(calls,[])
                finally:peer.close();control.close()
