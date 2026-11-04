"""Profile transfer preserves private authenticated P2P ingress evidence; model0."""
import os
from unittest import mock

from tests.test_xsm import TempState


class MigrationNetworkTest(TempState):
    def setUp(self):
        super().setUp()
        from tests import test_network_messages as fixture
        self.fixture = fixture.NetworkMessagesTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        from xsm import registry
        f = self.fixture
        self.old = registry.upsert('codex', f.b['home'], f.b['session_id'], os.getpid(), f.b['cwd'], name='old')
        home = str(f.root / 'successor')
        os.makedirs(home)
        self.new = registry.upsert('codex', home, f.b['session_id'], os.getpid(), f.b['cwd'], name='new')
        f.native(self.new)

    def move(self):
        from xsm import migration
        return migration.execute(migration.prepare(self.new, 'ref:' + self.old['ref']),
                                 authorize=lambda _: 'fixture user approval')

    def test_accepted_original_has_successor_admission_and_ack_readback(self):
        from tests import test_network_messages as fixture
        from xsm import envelope, handoff, network, receive
        f = self.fixture
        packet = f.prepare(kind='task', wake=False)
        f.gb.receive(fixture.A, packet)
        self.move()
        admitted = f.gb.ingress_record(packet['id'])
        self.assertEqual(handoff._identity(admitted['target_local']), handoff._identity(self.new))
        parsed = envelope.parse(handoff.status(self.new, packet['id'])['message']['content'])
        with mock.patch.object(network, 'message_gateway', return_value=f.gb), \
                mock.patch.object(network, 'call', return_value={'allowed': True}):
            self.assertIsNotNone(network.inbound_record(parsed, self.new))
            batch = receive.take_inbox_claims(self.new, owner={'type': 'native', 'id': 'successor'}, generation='new')
        self.assertTrue(batch['claims'], batch)
        token = batch['claims'][0]['token']
        handoff.ack(self.new, token, {'type': 'native', 'id': 'successor'}, 'new')
        state = f.gb.status(fixture.A, packet['id'], f.ap)
        self.assertTrue(state['acknowledged'])
        self.assertEqual(f.gb.receive(fixture.A, packet)['status'], 'acknowledged')

    def test_new_packet_to_old_endpoint_resolves_to_current_successor(self):
        from tests import test_network_messages as fixture
        from xsm import handoff, migration
        self.move()
        packet = self.fixture.prepare(wake=False)
        result = self.fixture.gb.receive(fixture.A, packet)
        self.assertTrue(result['stored'])
        self.assertEqual(handoff.status(self.new, packet['id'])['message']['body'], packet['body'])
        catchup = migration.status(self.new)['migrations'][0]['messages']
        self.assertEqual(catchup[0]['id'], packet['id'])
        self.assertIsNotNone(catchup[0]['addressed_via'])

    def test_forwarding_expiry_does_not_erase_an_already_accepted_receipt(self):
        from tests import test_network_messages as fixture
        from xsm import handoff, migration
        packet = self.fixture.prepare(wake=False)
        self.fixture.gb.receive(fixture.A, packet)
        receipt = self.move()
        with mock.patch('xsm.migration.time.time', return_value=receipt['forward_until']):
            state = self.fixture.gb.status(fixture.A, packet['id'], self.fixture.ap)
            self.assertTrue(state['stored'])
        self.assertEqual(handoff.status(self.new, packet['id'])['status'], 'pending')
