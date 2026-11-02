"""Pinned native CLI adapter. The existing plugin binds context before inference."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess

from xsm.native_workers import ProviderError
from .worker_cli import NativeCliError, build_command, parse_result

RUNTIME = 'opencode'
VERSION = '1.19.5'
CONTROL_PROTOCOL = 1


def default_home(caller):
    return os.environ.get('OPENCODE_CONFIG_DIR') or os.path.join(
        os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'opencode')


def _version(executable):
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'LANG', 'TMPDIR') if key in os.environ}
    try:
        result = subprocess.run([executable, '--version'], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProviderError('native OpenCode executable could not be verified') from error
    if result.returncode or result.stdout.strip() != VERSION:
        raise ProviderError('native OpenCode 1.19.5 is required')


def _installation(home):
    from xsm import host_install
    try:
        installed = host_install.inspect(RUNTIME, home)
        if installed['status'] != 'managed':
            raise ProviderError('install the owned xsm binding in the native OpenCode profile first')
        root = Path(installed['runtime_root'])
        frontend = root / 'integrations/opencode/xsm.mjs'
        data = frontend.read_bytes()
        if data != Path(__file__).with_name('xsm.mjs').read_bytes():
            raise ProviderError('update the native OpenCode binding before creating an owned service')
        return root, frontend, hashlib.sha256(data).hexdigest()
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ProviderError('native OpenCode xsm installation could not be verified') from error


def prepare(home):
    root, frontend, digest = _installation(home)
    selected = os.environ.get('XSM_OPENCODE') or shutil.which('opencode')
    if not selected or not os.path.isabs(selected):
        raise ProviderError('native OpenCode executable requires operator PATH or absolute XSM_OPENCODE')
    executable = os.path.realpath(selected)
    _version(executable)
    return {'executable': executable, 'version': VERSION, 'control_protocol': CONTROL_PROTOCOL,
            'runtime_root': str(root), 'frontend': str(frontend), 'frontend_sha256': digest}


def _admitted(worker):
    descriptor = worker.get('native_provider') or {}
    executable = descriptor.get('executable')
    if (descriptor.get('version') != VERSION or descriptor.get('control_protocol') != CONTROL_PROTOCOL
            or not isinstance(executable, str) or not os.path.isabs(executable)):
        raise ProviderError('native OpenCode worker lacks admitted executable metadata')
    root, frontend, digest = _installation(worker['home'])
    if any(descriptor.get(key) != value for key, value in (
            ('runtime_root', str(root)), ('frontend', str(frontend)), ('frontend_sha256', digest))):
        raise ProviderError('admitted native OpenCode binding changed; create a new owned service')
    return executable


def environment(worker, base):
    env = dict(base)
    for key in ('OPENCODE_CONFIG', 'OPENCODE_CONFIG_CONTENT', 'OPENCODE_SERVER_PASSWORD',
                'OPENCODE_SERVER_USERNAME', 'XSM_WORKER', 'XSM_OWNED_CONTROL_FD'):
        env.pop(key, None)
    env['OPENCODE_CONFIG_DIR'] = worker['home']
    return env


def argv(worker, context):
    executable = _admitted(worker)
    _version(executable)
    try:
        return build_command(executable, worker, context)
    except NativeCliError as error:
        raise ProviderError(str(error)) from error


def result(worker, context, output):
    _admitted(worker)
    try:
        return parse_result(output, context)
    except NativeCliError as error:
        raise ProviderError(str(error)) from error
