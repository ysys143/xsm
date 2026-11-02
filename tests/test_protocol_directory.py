"""Generic participant discovery retains native privacy and execution boundaries."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
from unittest import mock
from types import SimpleNamespace
from tests.test_xsm import TempState


class ProtocolDirectoryTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm.protocol import Connection
        subprocess.run(['git', 'init', '-q', '-b', 'main', self.tmp], check=True)
        self.connection = Connection(); self.addCleanup(self.connection.close)
        self.connection.dispatch('initialize', {'protocolVersion': '1'})
        self.a = self.open('a'); self.b = self.open('b')

    def open(self, conversation, cwd=None):
        return self.connection.dispatch('session.open', {'runtime': 'independent-fixture',
            'profile': 'private', 'conversation': conversation, 'cwd': cwd or self.tmp})

    def record(self, opened):
        return self.connection.sessions[opened['session']].record

    def discover(self):
        return self.connection.dispatch('operation.call', {'session': self.a['session'],
            'operation': 'xsm_discover', 'arguments': {}})

    def test_registered_generic_peers_discover_and_select_without_adding_homes(self):
        from xsm import config, directory, paths
        homes = Path(paths.path(config.HOMES))
        before = homes.read_bytes() if homes.exists() else None
        result = self.discover()
        self.assertEqual(result['status'], 'ok', result)
        peer = next(candidate for candidate in result['candidates'] if candidate['ref'] == self.b['ref'])
        selected = directory.resolve_candidate(self.record(self.a), peer['id'])
        self.assertEqual(selected['home'], self.record(self.b)['home'])
        self.assertEqual(selected['session_id'], self.record(self.b)['session_id'])
        self.assertEqual(homes.read_bytes() if homes.exists() else None, before)

    def test_unheld_forged_registration_is_not_visible(self):
        from xsm import paths, registry
        self.assertIn(self.b['ref'], [row['ref'] for row in self.discover()['candidates']])
        record = copy.deepcopy(self.record(self.b))
        record['session_id'] = hashlib.sha256(b'forged').hexdigest()
        record['ref'] = 'ffffff'
        filename = registry._record_path(record['runtime'], record['session_id'])
        paths.write_json(filename, record)
        Path(filename + '.protocol-lock').touch()
        self.assertNotIn('ffffff', [row['ref'] for row in self.discover()['candidates']])

    def test_publication_changes_visibility_but_not_communication_permission(self):
        from xsm import config, directory
        outside = Path(self.user_home) / 'other-repository'
        outside.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(outside)], check=True)
        third = self.open('outside', str(outside))
        self.assertNotIn(third['ref'], [row['ref'] for row in self.discover()['candidates']])
        directory.publish(self.record(third), user_source='explicit synthetic publication fixture')
        self.assertIn(third['ref'], [row['ref'] for row in self.discover()['candidates']])
        self.assertIsNone(config.scope_for(self.record(self.a), self.record(third))[0])

    def test_current_deny_policy_still_blocks_generic_selection(self):
        from xsm import config, network_directory, paths
        handle = network_directory.public_endpoint(self.record(self.b), 'a' * 64)
        self.assertIsNotNone(network_directory.resolve_local(handle, 'a' * 64))
        cfg = config.load(); cfg['deny'] = [self.b['ref']]; paths.write_json(paths.path(config.CONFIG), cfg)
        self.assertNotIn(self.b['ref'], [row['ref'] for row in self.discover()['candidates']])
        self.assertIsNone(network_directory.resolve_local(handle, 'a' * 64))

    def test_protocol_receiver_never_uses_a_legacy_native_queue_adapter(self):
        from xsm import adapters, handoff, network, network_directory
        receiver = self.record(self.b)
        handoff.store(receiver, {'id': 'protocol-wake', 'sender': self.record(self.a),
                      'body': 'retain exact original', 'content': 'native fixture content'})
        handoff.delivery(receiver, 'protocol-wake', 'pending', route='mcp-inbox')
        before = handoff.status(receiver, 'protocol-wake')
        daemon = object.__new__(network.Daemon)
        daemon.transport = SimpleNamespace(endpoint_id='a' * 64)
        packet = {'receiver': network_directory.public_endpoint(receiver, 'a' * 64),
                  'wake': True, 'id': 'protocol-wake', 'priority': 'next'}
        with mock.patch.object(network, 'native_reader_ready', return_value=True), \
                mock.patch.object(adapters, 'to_codex') as codex, mock.patch.object(adapters, 'to_claude') as claude:
            daemon.wake_native(packet)
            codex.assert_not_called(); claude.assert_not_called()
        self.assertEqual(handoff.status(receiver, 'protocol-wake'), before)

    def test_remote_identity_accepts_slugs_but_not_private_homes_or_separators(self):
        from xsm import network_identity
        endpoint = dict(machine='a' * 64, runtime='independent-fixture', home_id='b' * 64, session_id='conversation')
        self.assertEqual(network_identity.parse_target(network_identity.target(endpoint)), endpoint)
        for bad in (dict(endpoint, runtime='bad:runtime'), dict(endpoint, runtime='runtime\n'), dict(endpoint, home=self.tmp)):
            with self.assertRaises(ValueError):
                network_identity.endpoint(bad)

    def test_same_pid_resume_rotates_remote_generation_and_rejects_old_handle(self):
        from xsm import network_directory
        old = network_directory.public_endpoint(self.record(self.b), 'a' * 64)
        self.assertIsNotNone(old)
        self.connection.dispatch('session.close', {'session': self.b['session']})
        self.b = self.open('b')
        new = network_directory.public_endpoint(self.record(self.b), 'a' * 64)
        self.assertNotEqual(old['generation'], new['generation'])
        self.assertIsNone(network_directory.resolve_local(old, 'a' * 64))
        self.assertEqual(network_directory.resolve_local(new, 'a' * 64)['session_id'], new['session_id'])

    def test_local_selection_rejects_same_pid_replacement_during_lookup(self):
        from xsm import directory
        candidate = next(row for row in self.discover()['candidates'] if row['ref'] == self.b['ref'])
        original = directory._native_identity
        def replace_after_check(record, endpoint):
            result = original(record, endpoint)
            self.connection.dispatch('session.close', {'session': self.b['session']})
            self.b = self.open('b')
            return result
        with mock.patch.object(directory, '_native_identity', side_effect=replace_after_check):
            self.assertIsNone(directory.resolve_candidate(self.record(self.a), candidate['id']))

    def test_closed_participant_is_not_a_discovery_candidate_while_pid_lives(self):
        self.assertTrue(any(row['ref'] == self.b['ref'] for row in self.discover()['candidates']))
        self.connection.dispatch('session.close', {'session': self.b['session']})
        self.assertFalse(any(row['ref'] == self.b['ref'] for row in self.discover()['candidates']))

    def test_native_generation_bytes_remain_compatible(self):
        from xsm import network_directory
        from xsm import directory
        record = dict(runtime='codex', home=self.tmp, session_id='native', pid=os.getpid(), lstart='start', registered=True)
        fields = ('pid', 'lstart', 'mcp_pid', 'mcp_lstart', 'native_start', 'app_server')
        expected = network_directory._digest({'endpoint': directory._endpoint(record),
                    'execution': {key: record.get(key) for key in fields}})
        self.assertEqual(network_directory.public_endpoint(record, 'a' * 64)['generation'], expected)
