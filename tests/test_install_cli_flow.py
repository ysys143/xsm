"""P10 actual CLI subprocesses with isolated homes and passive discovery fixtures.

--fixture-cli runs the real argument parser/command. Discovery is restricted to
the fixture so another user's agent, account or home is never adopted. It does
not mock install/setup/doctor services. Fault cases are named separately.
--matrix-output writes the exact subprocess results for coordinator review.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
MATRIX = []


def fixture_cli():
    root = Path(os.environ['XSM_P10_FIXTURE_ROOT']).resolve()
    for name in ('HOME', 'XSM_HOME', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'XSM_P10_SOURCE'):
        assert os.path.commonpath((str(root), str(Path(os.environ[name]).resolve()))) == str(root), name
    sys.path.insert(0, os.environ['XSM_P10_SOURCE'])
    from xsm import cli, install, registry, setup_flow
    registry._running_codex = lambda: []
    registry.unregistered = lambda: []
    install.orphaned_servers = lambda: []
    install.codex_versions = lambda: []
    fault = os.environ.get('XSM_P10_FAULT')
    args = sys.argv[2:]
    if fault == 'cas':
        backup = install._backup
        def late_edit(filename):
            result = backup(filename)
            if filename.endswith(('settings.json', 'hooks.json')):
                Path(filename).write_text('{"sentinel":"late-user-edit"}')
                os.chmod(filename, 0o640)
            return result
        install._backup = late_edit
    elif fault == 'flow-replaced':
        write = install._cas_bytes
        switched = []
        def replace_flow(filename, *values, **kwargs):
            if filename.endswith(('settings.json', 'hooks.json')) and not switched:
                switched.append(True)
                runtime = 'claude' if filename.endswith('settings.json') else 'codex'
                with install.setup_write_guard(lambda: None):
                    setup_flow.begin({'runtime': runtime, 'home': str(Path(filename).parent)})
            return write(filename, *values, **kwargs)
        install._cas_bytes = replace_flow
    elif fault == 'runtime-copy':
        copy = install.shutil.copy2
        def interrupted(source, destination, *values, **kwargs):
            if '.new-' in str(destination):
                raise OSError('fixture runtime copy interrupted')
            return copy(source, destination, *values, **kwargs)
        install.shutil.copy2 = interrupted
    sys.exit(cli.main(args))


class InstallCliFlowTest(unittest.TestCase):
    def source(self, root):
        source = root / 'source'
        for part in ('xsm', 'hooks', 'skills', 'bin', '.claude-plugin', '.codex-plugin'):
            shutil.copytree(REPO / part, source / part, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(REPO / 'LICENSE', source / 'LICENSE')
        return source

    def environment(self, root, source):
        env = dict(os.environ)
        for key in list(env):
            if key.startswith(('XSM_', 'CLAUDE_', 'CODEX_', 'ORCA_')):
                env.pop(key)
        person = root / 'person'
        person.mkdir(exist_ok=True)
        env.update(HOME=str(person), XSM_HOME=str(root / 'state'), CODEX_HOME=str(person / '.codex'),
                   CLAUDE_CONFIG_DIR=str(person / '.claude'), PYTHONPATH=str(source),
                   PATH=str(root / 'tools') + os.pathsep + '/usr/bin:/bin',
                   XSM_P10_FIXTURE_ROOT=str(root), XSM_P10_SOURCE=str(source))
        return env

    def run_cli(self, root, env, argv, *, fault=None):
        env = dict(env)
        if fault:
            env['XSM_P10_FAULT'] = fault
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--fixture-cli'] + argv,
                                env=env, cwd=str(root), capture_output=True, text=True, timeout=35)
        return result

    def flows(self, root):
        states = []
        for filename in (root / 'state' / 'setup' / 'targets').glob('*.json'):
            pointer = json.loads(filename.read_text())
            states.append(json.loads((root / 'state' / 'setup' / 'flows' / (pointer['flow_id'] + '.json')).read_text()))
        return sorted(states, key=lambda value: (value['target']['runtime'], value['target']['home']))

    def plugin(self, home, source, runtime):
        version = json.loads((source / '.claude-plugin' / 'plugin.json').read_text())['version']
        cache = home / 'plugins' / 'cache' / 'xsm' / 'xsm' / version
        shutil.copytree(source, cache)
        if runtime == 'codex':
            (home / 'config.toml').write_text('[plugins."xsm@xsm"]\nenabled = true\n')
        else:
            (home / 'plugins' / 'installed_plugins.json').write_text(json.dumps({
                'plugins': {'xsm@xsm': [{'version': version, 'installPath': str(cache), 'scope': 'user'}]}}))

    def artifact(self, root, name, argv, result, states, **details):
        def clean(text):
            for path in (str(root.resolve()), str(root)):
                text = text.replace(path, '<fixture>')
            return text
        row = {'id': name, 'python': sys.version.split()[0], 'entry': 'real-cli-subprocess',
               'argv': [clean(value) for value in argv], 'returncode': result.returncode,
               'stdout': clean(result.stdout), 'stderr': clean(result.stderr),
               'flows': [{'flow_id': state['flow_id'], 'generation': state['generation'],
                          'status': state['status'], 'local_ready': state['local_ready'],
                          'steps': {key: value['status'] for key, value in state['steps'].items()}}
                         for state in states], 'first_roundtrip': 'unknown', 'G04': 'pending'}
        row.update(details)
        MATRIX.append(row)
        return row

    def test_named_install_matrix(self):
        topologies = (('single', 'claude'), ('single', 'codex'), ('multi', 'mixed'),
                      ('nondefault', 'claude'), ('nondefault', 'codex'))
        for initial, (topology, runtime), integration, mode in itertools.product(
                ('clean', 'installed'), topologies, ('direct', 'plugin'), ('snapshot', 'dev')):
            name = '/'.join((initial, topology, runtime, integration, mode))
            with self.subTest(cell=name), tempfile.TemporaryDirectory(prefix='xsm-p10-cli-matrix-') as directory:
                root = Path(directory)
                source = self.source(root)
                env = self.environment(root, source)
                if topology == 'multi':
                    homes = [('claude', root / 'person' / '.claude'), ('codex', root / 'profiles' / 'codex-second')]
                else:
                    home = root / 'person' / ('.' + runtime) if topology == 'single' else root / 'profiles' / (runtime + '-custom')
                    homes = [(runtime, home)]
                args = ['install', '--no-mcp', '--python', sys.executable]
                if mode == 'dev':
                    args.append('--dev')
                for kind, home in homes:
                    if integration == 'plugin':
                        self.plugin(home, source, kind)
                    args.extend(['--' + kind + '-home', str(home)])
                if integration == 'plugin':
                    args.append('--refresh')
                if initial == 'installed':
                    previous = self.run_cli(root, env, args)
                    self.assertEqual(previous.returncode, 0, previous.stdout + previous.stderr)
                result = self.run_cli(root, env, args)
                states = self.flows(root)
                row = self.artifact(root, name, args, result, states, initial=initial, topology=topology,
                                    runtime=runtime, integration=integration, requested_mode=mode,
                                    effective_mode='plugin-managed' if integration == 'plugin' else mode)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(len(states), len(homes))
                for state in states:
                    self.assertIn(state['flow_id'], result.stdout)
                    self.assertEqual(state['generation'], 2 if initial == 'installed' else 1)
                    self.assertEqual(state['steps']['harness']['status'], 'succeeded')
                    self.assertEqual(state['steps']['first-roundtrip']['status'], 'unknown')
                    self.assertEqual(state['status'], 'pending')
                doctor = self.run_cli(root, env, ['doctor', '--json'])
                self.assertEqual(doctor.returncode, 0, doctor.stderr)
                report = json.loads(doctor.stdout)
                self.assertIn('policy_health', report)
                self.assertNotIn('prerequisite',report['setup'])
                self.assertNotIn('gate',report['setup'])
                self.assertEqual(len(report['setup']['homes']), len(homes))
                for observed in report['setup']['homes']:
                    self.assertEqual(observed['first_roundtrip'], 'unknown')
                    self.assertTrue(all(value == 'unknown' for value in observed['capabilities'].values()))
                    self.assertIn(observed['flow']['flow_id'], result.stdout)
                row['doctor'] = report['setup']
                row['policy_health'] = report['policy_health']['health']
                row['status'] = 'passed'

    def fault_case(self, fault, *, malformed=False):
        with tempfile.TemporaryDirectory(prefix='xsm-p10-cli-fault-') as directory:
            root = Path(directory)
            source = self.source(root)
            env = self.environment(root, source)
            home = root / 'profile'
            home.mkdir()
            settings = home / 'hooks.json'
            settings.write_text('{broken' if malformed else '{"sentinel":"before"}')
            before = settings.read_bytes()
            args = ['install', '--codex-home', str(home), '--no-mcp', '--python', sys.executable]
            result = self.run_cli(root, env, args, fault=fault)
            states = self.flows(root)
            self.artifact(root, 'fault/' + (fault or 'invalid-settings'), args, result, states, fault=fault or 'invalid-settings')
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('setup flow ', result.stdout + result.stderr)
            if fault == 'cas':
                self.assertEqual(json.loads(settings.read_text()), {'sentinel': 'late-user-edit'})
                self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)
                self.assertEqual(states[0]['status'], 'failed')
            elif fault == 'flow-replaced':
                self.assertEqual(settings.read_bytes(), before)
                self.assertEqual(states[0]['generation'], 2)
                self.assertEqual(states[0]['status'], 'pending')
                self.assertIn('result-not-saved=StaleFlowError', result.stderr)
            else:
                self.assertEqual(settings.read_bytes(), before)
                self.assertEqual(states[0]['status'], 'failed')
            MATRIX[-1]['status'] = 'passed'

    def test_cli_cas_preserves_user_followup(self):
        self.fault_case('cas')

    def test_cli_replaced_flow_cannot_write_old_settings_or_completion(self):
        self.fault_case('flow-replaced')

    def test_cli_invalid_settings_have_failed_flow_without_overwrite(self):
        self.fault_case(None, malformed=True)

    def test_cli_failed_upgrade_keeps_old_snapshot_and_flow_id(self):
        with tempfile.TemporaryDirectory(prefix='xsm-p10-cli-upgrade-') as directory:
            root = Path(directory)
            source = self.source(root)
            env = self.environment(root, source)
            home = root / 'profile'
            args = ['install', '--codex-home', str(home), '--no-mcp', '--python', sys.executable]
            previous = self.run_cli(root, env, args)
            self.assertEqual(previous.returncode, 0, previous.stdout + previous.stderr)
            metadata = root / 'state' / 'runtime' / 'current.json'
            old = metadata.read_bytes()
            sid = json.loads(old)['id']
            old_reader = root / 'state' / 'runtime' / sid / 'xsm' / '__init__.py'
            reader_bytes = old_reader.read_bytes()
            with (source / 'xsm' / '__init__.py').open('a') as stream:
                stream.write('\n# isolated upgrade fixture\n')
            result = self.run_cli(root, env, args, fault='runtime-copy')
            states = self.flows(root)
            self.artifact(root, 'fault/runtime-copy', args, result, states, fault='runtime-copy')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(metadata.read_bytes(), old)
            self.assertEqual(old_reader.read_bytes(), reader_bytes)
            self.assertEqual(os.readlink(metadata.parent / 'current'), sid)
            self.assertEqual(states[0]['generation'], 2)
            self.assertEqual(states[0]['status'], 'failed')
            MATRIX[-1]['status'] = 'passed'

    def test_actual_module_command_and_doctor_text_table_keep_flow_and_policy_health(self):
        with tempfile.TemporaryDirectory(prefix='xsm-p10-cli-main-') as directory:
            root = Path(directory)
            source = self.source(root)
            env = self.environment(root, source)
            args = ['install', '--codex-home', str(root / 'profile'), '--no-mcp', '--python', sys.executable, '--dev']
            result = subprocess.run([sys.executable, '-m', 'xsm'] + args, cwd=root, env=env,
                                    capture_output=True, text=True, timeout=35)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            states = self.flows(root)
            row = self.artifact(root, 'module-entry/single/direct/dev', args, result, states)
            row['entry'] = 'python -m xsm'
            for argv in (['doctor'], ['doctor', '--table']):
                observed = self.run_cli(root, env, argv)
                self.assertEqual(observed.returncode, 0, observed.stderr)
                self.assertIn(states[0]['flow_id'], observed.stdout)
                self.assertIn('first-roundtrip=unknown', observed.stdout)
            policy = root / 'state' / 'config.json'
            policy.write_text('{broken')
            doctor = self.run_cli(root, env, ['doctor', '--json'])
            report = json.loads(doctor.stdout)
            self.assertEqual(report['policy_health']['source'], 'last-valid')
            self.assertFalse(report['policy_health']['can_grant'])
            self.assertIn('flow', report['setup']['homes'][0])
            table = self.run_cli(root, env, ['doctor', '--table'])
            self.assertIn('new grants disabled', table.stdout)
            self.assertIn(states[0]['flow_id'], table.stdout)
            row['policy_health_preserved'] = True
            row['status'] = 'passed'

    def test_mcp_registration_error_has_nonzero_result_failed_flow_and_redacted_output(self):
        with tempfile.TemporaryDirectory(prefix='xsm-p10-cli-mcp-') as directory:
            root = Path(directory)
            source = self.source(root)
            env = self.environment(root, source)
            tools = root / 'tools'
            tools.mkdir()
            native = tools / 'codex'
            native.write_text('#!/bin/sh\nprintf "fixture-secret-token\\n" >&2\nexit 7\n')
            native.chmod(0o755)
            args = ['install', '--codex-home', str(root / 'profile'), '--python', sys.executable]
            result = self.run_cli(root, env, args)
            states = self.flows(root)
            row = self.artifact(root, 'fault/native-mcp-registration', args, result, states,
                                native_cli='isolated-error-fixture')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(states[0]['status'], 'failed')
            self.assertNotIn('fixture-secret-token', result.stdout + result.stderr)
            self.assertIn('native MCP registration exited 7', result.stdout)
            row['status'] = 'passed'

    def _doctor_private_ledger(self, flags):
        """Exercise the real parser/doctor with stored messages, not a fake report."""
        with tempfile.TemporaryDirectory(prefix='xsm-p10-doctor-private-') as directory:
            root = Path(directory)
            source = self.source(root)
            env = self.environment(root, source)
            seed = '''
import json, time
from pathlib import Path
from xsm import ledger, paths
paths.ensure_home()
sender = dict(name='sender', alias='fixture', ref='aaaaaa', runtime='claude')
target = dict(name='target', alias='fixture', ref='bbbbbb', runtime='codex')
for mid in ('private-queued', 'private-unknown', 'private-error', 'blocked-1', 'blocked-2'):
    ledger.queued(mid, sender, target, 'dir:fixture', 'note',
                  'PRIVATE_BODY_' + mid + ' https://invite.invalid/' + mid)
    filename = Path(paths.path(paths.LEDGER, mid + '.json'))
    row = json.loads(filename.read_text())
    row['t'] = time.time() - 600
    row['body'] = 'PRIVATE_BODY_' + mid
    row['arbitrary'] = dict(message=dict(invite='https://invite.invalid/' + mid))
    row['to']['private'] = dict(body='PRIVATE_NESTED_TARGET')
    row['from']['ref'] = dict(body='PRIVATE_NESTED_ALLOWED_FIELD')
    filename.write_text(json.dumps(row))
ledger.unknown('private-unknown', 'PRIVATE_UNKNOWN_ERROR https://invite.invalid/unknown')
ledger.failed('private-error', 'PRIVATE_RAW_ERROR https://invite.invalid/error')
for mid in ('blocked-1', 'blocked-2'):
    ledger.failed(mid, 'sandbox-blocked: PRIVATE_ERROR_DETAIL https://invite.invalid/detail')
'''
            seeded = subprocess.run([sys.executable, '-c', seed], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(seeded.returncode, 0, seeded.stderr)
            ledger_dir = root / 'state' / 'ledger'
            before = {p.name: p.read_bytes() for p in ledger_dir.glob('*.json')}
            observed = self.run_cli(root, env, ['doctor'] + flags)
            self.assertEqual(observed.returncode, 0, observed.stdout + observed.stderr)
            after = {p.name: p.read_bytes() for p in ledger_dir.glob('*.json')}
            self.assertEqual(before, after, 'diagnosis must preserve original ledger bytes')
            for marker in ('PRIVATE_BODY_', 'https://invite.invalid/', 'PRIVATE_RAW_ERROR',
                           'PRIVATE_UNKNOWN_ERROR', 'PRIVATE_ERROR_DETAIL',
                           'PRIVATE_NESTED_TARGET', 'PRIVATE_NESTED_ALLOWED_FIELD'):
                self.assertNotIn(marker, observed.stdout + observed.stderr)
            return observed.stdout

    def test_doctor_json_selects_metadata_and_fixed_failure_categories(self):
        report = json.loads(self._doctor_private_ledger(['--json']))
        stuck = report['stuck']
        self.assertEqual([r['id'] for r in stuck['undelivered']], ['private-queued'])
        self.assertEqual([r['id'] for r in stuck['uncertain']], ['private-unknown'])
        self.assertEqual(stuck['send_failures'], {'sandbox-blocked': 2, 'other': 1})
        for row in stuck['undelivered'] + stuck['uncertain']:
            self.assertEqual(set(row), {'id', 'status', 't', 'from', 'to'})
            self.assertIn(row['status'], ('queued', 'unknown'))
            self.assertIsInstance(row['t'], (int, float))
            self.assertEqual(row['from'], {'name': 'sender', 'alias': 'fixture',
                                          'runtime': 'claude'})
            self.assertEqual(row['to'], {'name': 'target', 'alias': 'fixture',
                                        'ref': 'bbbbbb', 'runtime': 'codex'})

    def test_doctor_text_never_uses_private_errors_as_failure_labels(self):
        text = self._doctor_private_ledger([])
        self.assertIn('sender -> target is still queued: private-queued', text)
        self.assertIn('sender -> target may or may not have arrived: private-unknown', text)
        self.assertIn('2 send(s) failed with sandbox-blocked', text)
        self.assertIn('1 send(s) failed with other', text)

    def test_doctor_table_does_not_disclose_stored_message_or_error(self):
        text = self._doctor_private_ledger(['--table'])
        self.assertIn('| check | result |', text)
        self.assertIn('state', text)

    def test_actual_cli_upgrade_preserves_live_reader_and_reports_only_passive_observations(self):
        with tempfile.TemporaryDirectory(prefix='xpr-') as directory:
            root = Path(directory)
            source = self.source(root)
            env = self.environment(root, source)
            home = root / 'person' / '.claude'
            args = ['install', '--claude-home', str(home), '--no-mcp', '--python', sys.executable, '--refresh']
            initial = self.run_cli(root, env, args)
            self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
            metadata = root / 'state' / 'runtime' / 'current.json'
            old = json.loads(metadata.read_text())['id']
            filename = metadata.parent / old / 'xsm' / '__init__.py'
            original = filename.read_text()
            socket_path = root / 's'
            program = ('import pathlib,socket,sys; p=pathlib.Path(sys.argv[1]); '
                       's=socket.socket(socket.AF_UNIX); s.bind(sys.argv[2]); s.listen(); '
                       'print("ready",flush=True); sys.stdin.readline(); print(p.read_text())')
            reader = subprocess.Popen([sys.executable, '-c', program, str(filename), str(socket_path)],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(reader.stdout.readline().strip(), 'ready')
                started = subprocess.run(['ps', '-o', 'lstart=', '-p', str(reader.pid)],
                                         capture_output=True, text=True, check=True).stdout.strip()
                pointer = root / 'state' / 'sessions' / 'claude-fixture-reader.json'
                pointer.write_text(json.dumps({'runtime': 'claude', 'home': str(home.resolve()),
                    'session_id': 'fixture-reader', 'pid': reader.pid, 'lstart': started,
                    'cwd': str(root), 'ref': 'aabbcc', 'registered': True, 'socket': str(socket_path)}))
                with (source / 'xsm' / '__init__.py').open('a') as stream:
                    stream.write('\n# actual CLI upgrade fixture\n')
                result = self.run_cli(root, env, args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotEqual(json.loads(metadata.read_text())['id'], old)
                self.assertTrue(filename.exists())
                self.assertIsNone(reader.poll())
                doctor = self.run_cli(root, env, ['doctor', '--json'])
                observed = json.loads(doctor.stdout)['setup']['homes'][0]
                self.assertEqual(observed['process'], 'observed')
                self.assertEqual(observed['socket'], 'observed')
                self.assertEqual(observed['first_roundtrip'], 'unknown')
                self.assertTrue(all(value == 'unknown' for value in observed['capabilities'].values()))
                row = self.artifact(root, 'upgrade/live-owned-reader', args, result, self.flows(root),
                                    old_runtime_preserved=True, passive_readback=observed,
                                    process_kind='owned-fixture-reader')
                output, error = reader.communicate('\n', timeout=10)
                self.assertEqual(reader.returncode, 0, error)
                self.assertEqual(output, original + '\n')
                row['status'] = 'passed'
            finally:
                if reader.poll() is None:
                    reader.kill()
                    reader.communicate(timeout=5)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--fixture-cli':
        fixture_cli()
    elif len(sys.argv) > 2 and sys.argv[1] == '--matrix-output':
        output = Path(sys.argv[2])
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(InstallCliFlowTest)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        output.write_text(json.dumps({'python': sys.version.split()[0], 'passed': result.wasSuccessful(),
                                      'cells': MATRIX}, ensure_ascii=False, indent=2) + '\n')
        sys.exit(0 if result.wasSuccessful() else 1)
    else:
        unittest.main()
