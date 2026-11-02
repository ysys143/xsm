"""Generic protocol actors over two real private QUIC services; no native model/UI."""
import unittest
from tests import test_network_application as application


class ProtocolNetworkTest(unittest.TestCase):
    def setUp(self):
        from xsm.protocol import Connection
        self.case = application.NetworkApplicationTests(
            'test_git_discover_resolve_task_native_file_consume_reverse_reply_and_question_correlation')
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.connections, self.sessions = [], []
        for node, old, name in ((self.case.a, self.case.actor_a, 'a'), (self.case.b, self.case.actor_b, 'b')):
            with self.case.local(node):
                connection = Connection()
                connection.dispatch('initialize', {'protocolVersion': '1'})
                session = connection.dispatch('session.open', {'runtime': 'independent-network',
                    'profile': 'private', 'conversation': name, 'cwd': old['cwd']})
            self.connections.append(connection); self.sessions.append(session)
            self.addCleanup(self.close, node, connection)
        self.refresh()
        self.case.map_repositories()

    def close(self, node, connection):
        with self.case.local(node):
            connection.close()

    def refresh(self):
        self.case.actor_a, self.case.actor_b = [connection.sessions[session['session']].record
            for connection, session in zip(self.connections, self.sessions)]

    def call(self, index, operation, **arguments):
        node = (self.case.a, self.case.b)[index]
        with self.case.local(node):
            return self.connections[index].dispatch('operation.call', {'session': self.sessions[index]['session'],
                'operation': operation, 'arguments': arguments})

    def test_real_service_generic_body_claim_ack_and_reverse_reply(self):
        sent = self.case.send(request_id='generic-network-task', body='exact generic task')
        self.assertTrue(sent['delivery']['stored'])
        self.assertFalse(sent['delivery']['acknowledged'])
        pack = self.call(1, 'xsm_inbox')
        self.assertEqual([claim['id'] for claim in pack['claims']], ['generic-network-task'])
        self.assertIn('exact generic task', pack['messages'][0])
        self.assertEqual(self.call(1, 'xsm_ack', tokens=[claim['token'] for claim in pack['claims']])['acked'], ['generic-network-task'])
        self.case.send(self.case.b, self.case.actor_b, self.case.target(self.case.a, self.case.actor_a),
            'generic-network-reply', kind='reply', reply_to='generic-network-task', outcome='succeeded', body='exact answer')
        reply = self.call(0, 'xsm_inbox')
        self.assertEqual([claim['id'] for claim in reply['claims']], ['generic-network-reply'])
        self.assertIn('exact answer', reply['messages'][0])
        self.assertEqual(self.call(0, 'xsm_ack', tokens=[claim['token'] for claim in reply['claims']])['acked'], ['generic-network-reply'])

    def test_accepted_original_survives_same_conversation_new_execution(self):
        self.assertTrue(self.case.send(request_id='generic-before-resume')['delivery']['stored'])
        old = self.case.actor_b
        with self.case.local(self.case.b):
            self.connections[1].dispatch('session.close', {'session': self.sessions[1]['session']})
            self.sessions[1] = self.connections[1].dispatch('session.open', {'runtime': old['runtime'],
                'profile': 'private', 'conversation': 'b', 'cwd': old['cwd']})
        self.refresh()
        pack = self.call(1, 'xsm_inbox')
        self.assertEqual([claim['id'] for claim in pack['claims']], ['generic-before-resume'], pack)
        self.assertEqual(self.call(1, 'xsm_ack', tokens=[claim['token'] for claim in pack['claims']])['acked'], ['generic-before-resume'])
