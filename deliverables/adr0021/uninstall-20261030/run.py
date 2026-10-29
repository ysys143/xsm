"""Bounded isolated public-CLI uninstall observation; no model invocation."""
from pathlib import Path
import datetime, hashlib, json, os, shutil, socket, stat, subprocess, sys, time

ACTIVE = json.loads(Path('/private/tmp/adr21-uninstall-active.json').read_text())
ROOT, OUT = Path(ACTIVE['root']), Path(ACTIVE['out'])
META = json.loads((ROOT / 'run.json').read_text())
FROZEN = Path(META['frozen'])
PYTHON = '/usr/bin/python3'
BOOT = str(FROZEN / 'bin/xsm')
LINK = str(ROOT / 'home/.local/bin/xsm')
BINARY = str(FROZEN / 'native/xsm-net/target/release/xsm-net')
ENV = {k: v for k, v in os.environ.items()
       if not k.startswith(('XSM_', 'CODEX_', 'CLAUDE_', 'ANTHROPIC_', 'OPENAI_', 'OTEL_'))}
ENV.update(HOME=str(ROOT / 'home'), XSM_HOME=str(ROOT / 'state'), CODEX_HOME=str(ROOT / 'codex-a'),
           CLAUDE_CONFIG_DIR=str(ROOT / 'home/empty-claude'), XDG_CONFIG_HOME=str(ROOT / 'home/config'),
           TMPDIR=str(ROOT / 'tmp'), XSM_PYTHON=PYTHON, XSM_NET_BINARY=BINARY,
           PYTHONDONTWRITEBYTECODE='1', PATH=str(ROOT / 'home/.local/bin') + os.pathsep + ENV.get('PATH', os.defpath))
PEER = dict(ENV, XSM_HOME=str(ROOT / 'peer-state'), CODEX_HOME=str(ROOT / 'codex-peer'))
RESULT = {'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'commands': [],
          'new_model_calls': 0, 'interactive_prompts': 0, 'checks': {}, 'cleanup': {}}
running = set()

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def checkpoint():
    (OUT / 'results.json').write_text(json.dumps(RESULT, ensure_ascii=False, indent=2) + '\n')

def command(label, args, env=ENV, cli=None, timeout=45):
    argv = [cli or (LINK if Path(LINK).exists() else BOOT), *args]
    started = time.monotonic()
    process = subprocess.run(argv, env=env, cwd=ROOT, capture_output=True, timeout=timeout)
    row = {'label': label, 'argv': argv, 'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'seconds': round(time.monotonic() - started, 3), 'exit_code': process.returncode,
           'stdout_bytes': len(process.stdout), 'stderr_bytes': len(process.stderr)}
    for suffix, raw in (('stdout', process.stdout), ('stderr', process.stderr)):
        p = ROOT / 'logs' / (label + '.' + suffix)
        with os.fdopen(os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(raw)
        row[suffix + '_sha256'] = hashlib.sha256(raw).hexdigest()
    RESULT['commands'].append(row); checkpoint()
    print(json.dumps({'step': label, 'exit_code': process.returncode, 'seconds': row['seconds']}), flush=True)
    if process.returncode:
        raise RuntimeError('public-cli-failed:' + label)
    try:
        return json.loads(process.stdout)
    except ValueError:
        return None

def tree(path):
    answer = {}
    for p in sorted(Path(path).rglob('*')):
        rel = str(p.relative_to(path))
        if p.is_symlink(): answer[rel] = {'link': os.readlink(p)}
        elif p.is_file(): answer[rel] = {'sha256': digest(p)}
    return answer

def key_metadata(path):
    s = Path(path).stat()
    return {'inode': s.st_ino, 'size': s.st_size, 'mtime_ns': s.st_mtime_ns, 'mode': stat.S_IMODE(s.st_mode)}

def assert_stopped(status, env):
    # Hash-derived socket uses the private TMPDIR and private XSM_HOME only.
    key = hashlib.sha256(os.path.realpath(env['XSM_HOME']).encode()).hexdigest()[:24]
    location = ROOT / 'tmp' / ('xsm-net-%d' % os.getuid()) / (key + '.sock')
    deadline = time.monotonic() + 5
    while location.exists() and time.monotonic() < deadline: time.sleep(.05)
    assert not location.exists(), 'private control socket remains'
    observed = subprocess.run(['ps', '-p', str(status['service_pid']) + ',' + str(status['engine_pid']),
                              '-o', 'pid=,ppid=,uid=,stat=,comm='], capture_output=True, text=True)
    assert not observed.stdout.strip(), 'owned service/engine PID remains'
    rebound = []
    for address in status['transport']['bound_addresses']:
        if address.startswith('['):
            ip, port = address[1:].split(']:'); family = socket.AF_INET6
        else:
            ip, port = address.rsplit(':', 1); family = socket.AF_INET
        with socket.socket(family, socket.SOCK_DGRAM) as probe:
            probe.bind((ip, int(port)))
        rebound.append(address)
    return {'control_socket_remaining': False, 'recorded_pids_remaining': False,
            'UDP_rebind_success_count': len(rebound), 'all_bound_UDP_addresses_rebound': True}

def profile_removed(name):
    p = ROOT / name
    config = (p / 'config.toml').read_text()
    hooks = json.loads((p / 'hooks.json').read_text())
    assert '[mcp_servers.xsm]' not in config
    assert '[mcp_servers.keep_user]' in config and 'persistence = "none"' in config
    assert 'sandbox_mode = "read-only"' in config
    assert hooks == {'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': '/usr/bin/true private-user-hook'}]}]}}
    assert not (p / 'skills/xsm').exists()
    for rel in ('skills/keep-user/SKILL.md', 'user-marker.txt'):
        assert digest(p / rel) == META['initial_custom_profile_hashes'][name][rel]
    return {'xsm_MCP_absent': True, 'xsm_skill_absent': True, 'custom_hook_exact': True,
            'custom_MCP_and_settings_preserved': True, 'custom_skill_marker_preserved': True}

try:
    assert digest(BINARY) == json.loads((FROZEN / 'freeze.json').read_text())['binary_sha256']
    RESULT['frozen_manifest_sha256'] = digest(FROZEN / 'manifest.json')
    command('install-a', ['install', '--codex-home', str(ROOT / 'codex-a'), '--python', PYTHON], cli=BOOT)
    command('install-b', ['install', '--codex-home', str(ROOT / 'codex-b'), '--python', PYTHON], cli=BOOT)
    assert Path(LINK).is_symlink()
    command('configure-shared', ['network', 'configure', '--relay', 'off', '--port', '0'])
    main = command('init-shared', ['network', 'init', 'private-uninstall-evaluation']); running.add('main')
    command('configure-peer', ['network', 'configure', '--relay', 'off', '--port', '0'], env=PEER)
    invitation = command('invite-private', ['network', 'invite'])
    peer = command('join-peer', ['network', 'join', '--ticket-file', invitation['ticket_file']], env=PEER); running.add('peer')
    main = command('shared-before-uninstall', ['network', 'status'])
    assert main['active'] and peer['active']
    assert len(main['network']['members']) == len(peer['network']['members']) == 2
    key = ROOT / 'state/network/transport/node.secret'
    key_before = key_metadata(key)
    custom_before = digest(ROOT / 'state/config.json')
    original_before = digest(ROOT / 'state/owner-original.txt')
    profile_b_before = tree(ROOT / 'codex-b')
    runtime_before = tree(ROOT / 'state/runtime')
    command('uninstall-a-shared-service-live', ['uninstall', '--codex-home', str(ROOT / 'codex-a')])
    kept = command('shared-after-a-removal', ['network', 'status'], env=dict(ENV, CODEX_HOME=str(ROOT / 'codex-b')))
    assert kept['service_pid'] == main['service_pid'] and kept['engine_pid'] == main['engine_pid']
    assert kept['active'] and Path(LINK).is_symlink()
    assert tree(ROOT / 'codex-b') == profile_b_before
    RESULT['checks']['single_home_removal'] = dict(profile_removed('codex-a'), shared_service_same_live_PID=True,
                                                   other_home_exactly_unchanged=True, CLI_link_preserved=True)
    command('explicit-network-stop', ['network', 'stop'], env=dict(ENV, CODEX_HOME=str(ROOT / 'codex-b')))
    RESULT['checks']['after_explicit_stop'] = assert_stopped(main, ENV); running.remove('main')
    command('uninstall-b-after-explicit-stop', ['uninstall', '--codex-home', str(ROOT / 'codex-b')])
    RESULT['checks']['last_home_removal'] = dict(profile_removed('codex-b'), CLI_link_removed=not Path(LINK).exists())
    assert not Path(LINK).exists()
    assert key_metadata(key) == key_before
    assert digest(ROOT / 'state/config.json') == custom_before
    assert digest(ROOT / 'state/owner-original.txt') == original_before
    assert tree(ROOT / 'state/runtime') == runtime_before
    RESULT['checks']['preservation'] = {'key_metadata_unchanged': True, 'key_values_read': False,
        'custom_XSM_configuration_bytes_unchanged': True, 'original_bytes_unchanged': True,
        'runtime_copies_retained_unchanged': True, 'private_auth_files_absent': all(not (ROOT / p / 'auth.json').exists()
            for p in ('codex-a', 'codex-b', 'codex-peer'))}
    RESULT['completed'] = True
except Exception as error:
    RESULT['completed'] = False; RESULT['failure'] = str(error) if isinstance(error, (RuntimeError, AssertionError)) else type(error).__name__
finally:
    for role in list(running):
        env = ENV if role == 'main' else PEER
        try:
            status = command('cleanup-status-' + role, ['network', 'status'], env=env, cli=BOOT)
            command('cleanup-stop-' + role, ['network', 'stop'], env=env, cli=BOOT)
            RESULT['cleanup'][role] = assert_stopped(status, env)
        except Exception as error: RESULT['cleanup'][role] = {'error': type(error).__name__}
    RESULT['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat(); checkpoint()
print(json.dumps({'completed': RESULT.get('completed'), 'failure': RESULT.get('failure'),
                  'steps': len(RESULT['commands']), 'checks': RESULT['checks'], 'cleanup': RESULT['cleanup']}, ensure_ascii=False), flush=True)
