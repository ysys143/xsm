"""Pinned OpenClaw backend adapter. Shared workers own reservations and replies."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from xsm.native_workers import ProviderError
from .worker_cli import parse_result
from .worker_session import NativeSessionError
from .worker_transport import NativeRpc

RUNTIME = 'openclaw'
VERSION = '2026.10.9'
CONTROL_PROTOCOL = 1
FILES = ('xsm.mjs', 'worker_cli.py', 'worker_frontend.py', 'worker_rpc.mjs',
         'worker_transport.py', 'worker_session.py')


def default_home(caller):
    return os.environ.get('OPENCLAW_STATE_DIR') or os.path.expanduser('~/.openclaw')


def _installation(home):
    from xsm import host_install
    try:
        installed = host_install.inspect(RUNTIME, home)
        if installed['status'] != 'managed':
            raise ProviderError('install the owned xsm binding in the OpenClaw profile first')
        root = Path(installed['runtime_root'])
        folder = root / 'integrations/openclaw'
        hashes = {}
        for name in FILES:
            data = (folder / name).read_bytes()
            if data != Path(__file__).with_name(name).read_bytes():
                raise ProviderError('update the native OpenClaw binding before creating an owned service')
            hashes[name] = hashlib.sha256(data).hexdigest()
        return root, folder / 'worker_cli.py', hashes
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ProviderError('native OpenClaw installation could not be verified') from error


def _package(executable):
    try:
        info = json.loads(Path(executable).with_name('package.json').read_text())
    except (OSError, ValueError) as error:
        raise ProviderError('native OpenClaw package could not be verified') from error
    if info.get('name') != 'openclaw' or info.get('version') != VERSION:
        raise ProviderError('native OpenClaw 2026.10.9 is required')


def _environment(home, base):
    env = dict(base)
    for key in ('OPENCLAW_PROFILE', 'XSM_WORKER', 'XSM_OWNED_CONTROL_FD'):
        env.pop(key, None)
    env.update(OPENCLAW_STATE_DIR=home, OPENCLAW_CONFIG_PATH=os.path.join(home, 'openclaw.json'))
    return env


def prepare(home):
    root, frontend, hashes = _installation(home)
    executable = os.environ.get('XSM_OPENCLAW') or shutil.which('openclaw')
    node = os.environ.get('XSM_OPENCLAW_NODE') or shutil.which('node')
    if any(not isinstance(path, str) or not os.path.isabs(path) or not os.access(path, os.X_OK)
           for path in (executable, node)):
        raise ProviderError('operator native CLI and Node paths are required')
    executable, node = os.path.realpath(executable), os.path.realpath(node)
    _package(executable)
    try:
        roster = NativeRpc(node, executable, cwd=os.getcwd(), env=_environment(home, os.environ))('agents.list', {})
        selected = os.environ.get('XSM_OPENCLAW_AGENT_ID')
        if selected is None and roster.get('selectionRequired') is not True:
            selected = roster.get('defaultId')
        agents = roster.get('agents')
        if (not isinstance(selected, str) or not selected or not isinstance(agents, list)
                or sum(isinstance(row, dict) and row.get('id') == selected for row in agents) != 1):
            raise ProviderError('select an exact native agent with XSM_OPENCLAW_AGENT_ID')
    except NativeSessionError as error:
        raise ProviderError('native OpenClaw agent roster unavailable') from error
    return {'executable': executable, 'node': node, 'python': sys.executable,
            'version': VERSION, 'control_protocol': CONTROL_PROTOCOL, 'agent_id': selected,
            'runtime_root': str(root), 'frontend': str(frontend),
            'frontend_sha256': hashes['worker_cli.py'], 'binding_hashes': hashes}


def _admitted(worker):
    descriptor = worker.get('native_provider') or {}
    if descriptor.get('version') != VERSION or descriptor.get('control_protocol') != CONTROL_PROTOCOL:
        raise ProviderError('native OpenClaw worker lacks admitted metadata')
    for key in ('executable', 'node', 'python', 'frontend'):
        if not isinstance(descriptor.get(key), str) or not os.path.isabs(descriptor[key]):
            raise ProviderError('native OpenClaw worker lacks admitted runtime paths')
    root, frontend, hashes = _installation(worker['home'])
    if (descriptor.get('runtime_root') != str(root) or descriptor['frontend'] != str(frontend)
            or descriptor.get('binding_hashes') != hashes):
        raise ProviderError('native OpenClaw binding changed; create a new owned service')
    _package(descriptor['executable'])
    return descriptor


def environment(worker, base):
    return _environment(worker['home'], base)


def argv(worker, context):
    descriptor = _admitted(worker)
    args = [descriptor['python'], '-B', descriptor['frontend'], '--node', descriptor['node'],
            '--native-cli', descriptor['executable'], '--agent-id', descriptor['agent_id'],
            '--cwd', worker['cwd'], '--context-id', context['id'], '--context-epoch', context['epoch'],
            '--run-id', 'xsm-owned-' + worker['id'] + '-' + uuid.uuid4().hex]
    for value, flag in ((context.get('native_session_id'), '--native-session-id'),
                        (worker.get('model'), '--model'), (worker.get('effort'), '--thinking')):
        if value is not None:
            if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
                raise ProviderError('invalid native OpenClaw turn option')
            args += [flag + '=' + value]
    return args


def result(worker, context, output):
    descriptor = _admitted(worker)
    try:
        return parse_result(output, context, agent_id=descriptor['agent_id'], cwd=worker['cwd'])
    except NativeSessionError as error:
        raise ProviderError(str(error)) from error
