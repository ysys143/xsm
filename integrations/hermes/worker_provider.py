"""Pinned native Hermes owned CLI adapter; no policy, grants or work journal."""
from __future__ import annotations

import os
import hashlib
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from xsm.native_workers import ProviderError
from .worker_cli import NativeCliError, build_command, parse_result

RUNTIME = 'hermes'
VERSION = '0.22.5'
CONTROL_PROTOCOL = 1


def default_home(caller):
    # Generic protocol homes are opaque xsm projections, not native profile paths.
    return os.environ.get('HERMES_HOME') or os.path.expanduser('~/.hermes')


def _version(executable, home, *, python=False):
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR', 'HOME', 'PYTHONPATH') if key in os.environ}
    env.update(HERMES_HOME=home, PYTHONDONTWRITEBYTECODE='1')
    try:
        command = [executable, '-m', 'hermes_cli.main', '--version'] if python else [executable, '--version']
        result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProviderError('native Hermes executable could not be verified') from error
    if result.returncode or not re.search(r'(?<![0-9A-Za-z_.])v?0\.22\.5(?![0-9A-Za-z_.+-])', result.stdout):
        raise ProviderError('native Hermes 0.22.5 is required')


def _python_for_cli(executable, home):
    selected = os.environ.get('XSM_HERMES_PYTHON')
    if not selected:
        try:
            with open(executable, 'rb') as stream:
                first = stream.readline(4096).decode('utf-8').strip()
                second = stream.readline(4096).decode('utf-8').strip()
            words = shlex.split(first[2:]) if first.startswith('#!') else []
            if words and words[0] in ('/bin/sh', '/usr/bin/sh'):
                prefix, suffix = "'''exec' ", ' "$0" "$@"'
                words = shlex.split(second[len(prefix):-len(suffix)]) if second.startswith(prefix) and second.endswith(suffix) else []
            if len(words) == 2 and words[0] in ('/usr/bin/env', '/bin/env'):
                words = [shutil.which(words[1]) or '']
            if len(words) == 1:
                selected = words[0]
        except (OSError, UnicodeError, ValueError) as error:
            raise ProviderError('native Hermes Python launcher could not be inspected') from error
    if (not isinstance(selected, str) or not os.path.isabs(selected)
            or not os.path.isfile(selected) or not os.access(selected, os.X_OK)):
        raise ProviderError('native Hermes Python must be supplied by its launcher or absolute XSM_HERMES_PYTHON')
    # Keep the venv spelling: realpath would discard its pyvenv.cfg/site-packages.
    selected = os.path.abspath(selected)
    _version(selected, home, python=True)
    return selected


def prepare(home):
    from xsm import host_install
    try:
        installed = host_install.inspect(RUNTIME, home)
    except (OSError, ValueError) as error:
        raise ProviderError('native Hermes xsm installation could not be verified') from error
    if installed['status'] != 'managed':
        raise ProviderError('install the owned xsm binding in the native Hermes profile first')
    selected = os.environ.get('XSM_HERMES') or shutil.which('hermes')
    if not selected or not os.path.isabs(selected):
        raise ProviderError('native Hermes executable must come from operator PATH or absolute XSM_HERMES')
    executable = os.path.realpath(selected)
    _version(executable, home)
    python = _python_for_cli(executable, home)
    frontend = Path(__file__).with_name('worker_frontend.py').resolve()
    return {'executable': executable, 'version': VERSION, 'python': python,
            'control_protocol': CONTROL_PROTOCOL, 'frontend': str(frontend),
            'runtime_root': str(frontend.parents[2]),
            'frontend_sha256': hashlib.sha256(frontend.read_bytes()).hexdigest()}


def _admitted(worker):
    descriptor = worker.get('native_provider') or {}
    executable = descriptor.get('executable')
    if (descriptor.get('version') != VERSION or not isinstance(executable, str)
            or not os.path.isabs(executable)):
        raise ProviderError('native Hermes worker lacks admitted executable metadata')
    return executable


def environment(worker, base):
    env = dict(base)
    for key in list(env):
        if key.startswith(('HERMES_SESSION_', 'HERMES_TUI_')) or key in (
                'HERMES_PROFILE', 'HERMES_API_KEY', 'CUSTOM_API_KEY', 'XSM_WORKER', 'XSM_OWNED_CONTROL_FD'):
            env.pop(key, None)
    env.update(HERMES_HOME=worker['home'], TERMINAL_CWD=worker['cwd'])
    return env


def argv(worker, context):
    executable = _admitted(worker)
    _version(executable, worker['home'])
    descriptor = worker['native_provider']
    python, frontend = descriptor.get('python'), descriptor.get('frontend')
    if (descriptor.get('control_protocol') != CONTROL_PROTOCOL or not isinstance(python, str)
            or not os.path.isabs(python) or not isinstance(frontend, str) or not os.path.isabs(frontend)):
        raise ProviderError('native Hermes worker lacks its admitted pre-turn frontend')
    _version(python, worker['home'], python=True)
    try:
        if hashlib.sha256(Path(frontend).read_bytes()).hexdigest() != descriptor.get('frontend_sha256'):
            raise ProviderError('admitted native frontend changed; create a new owned service')
    except OSError as error:
        raise ProviderError('admitted native frontend is unavailable') from error
    try:
        return [python, '-B', frontend, *build_command(executable, worker, context)[1:]]
    except NativeCliError as error:
        raise ProviderError(str(error)) from error


def result(worker, context, output):
    _admitted(worker)
    try:
        return parse_result(output, context)
    except NativeCliError as error:
        raise ProviderError(str(error)) from error
