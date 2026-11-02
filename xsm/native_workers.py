"""Load owned CLI adapters from the installation's fixed native provider catalog.

A model selects a catalog runtime, never an executable, import name or code path.
The registry handles dispatch only; owned requests and policy remain in workers.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import types

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ('claude', 'codex')
_SLUG = re.compile(r'[a-z][a-z0-9-]{0,63}\Z')
_LOAD_LOCK = threading.RLock()


class ProviderError(ValueError):
    pass


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ProviderError('duplicate native worker catalog entry')
        value[key] = item
    return value


def _catalog():
    filename = ROOT / 'integrations/worker-providers.json'
    try:
        if filename.is_symlink():
            raise ProviderError('native worker catalog symlink refused')
        value = json.loads(filename.read_text(), object_pairs_hook=_unique)
    except (OSError, ValueError) as error:
        raise ProviderError('invalid native worker catalog') from error
    if not isinstance(value, dict):
        raise ProviderError('invalid native worker catalog')
    result = {}
    for runtime, relative in value.items():
        if (not isinstance(runtime, str) or not _SLUG.fullmatch(runtime) or runtime in LEGACY
                or relative != 'integrations/' + runtime + '/worker_provider.py'):
            raise ProviderError('invalid native worker provider entry')
        path = ROOT / relative
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
            raise ProviderError('native worker provider must be an owned installation file')
        result[runtime] = path
    return result


def runtimes():
    return list(LEGACY) + sorted(_catalog())


def configured_roots():
    """Logical owned services retain their admitted frontend even between turns."""
    from . import paths
    roots = []
    folder = paths.path('workers')
    try:
        directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return roots
    except OSError as error:
        raise ProviderError('owned worker references are unavailable') from error
    records = []
    try:
        for name in os.listdir(directory):
            if not name.endswith('.json'):
                continue
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd) as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                    raise ProviderError('invalid owned worker reference file')
                worker = json.load(stream, object_pairs_hook=_unique)
            if not isinstance(worker, dict) or worker.get('name') != name[:-5]:
                raise ProviderError('invalid owned worker reference')
            records.append(worker)
    except (OSError, ValueError, UnicodeError) as error:
        raise ProviderError('owned worker references could not be verified') from error
    finally:
        os.close(directory)
    for worker in records:
        descriptor = worker.get('native_provider')
        if descriptor is None:
            continue
        if not isinstance(descriptor, dict):
            raise ProviderError('invalid owned native provider reference')
        frontend = descriptor.get('frontend')
        if frontend is None and descriptor.get('control_protocol') is None:
            continue
        if not isinstance(frontend, str) or not Path(frontend).is_absolute():
            raise ProviderError('owned native frontend reference unavailable')
        path = Path(frontend)
        if len(path.parents) < 3:
            raise ProviderError('invalid owned native frontend reference')
        root = descriptor.get('runtime_root') or str(path.parents[2])
        if (not isinstance(root, str) or not Path(root).is_absolute()
                or path.parent != Path(root) / 'integrations' / str(worker.get('runtime'))):
            raise ProviderError('owned native runtime reference differs from frontend')
        roots.append(root)
    return roots


def provider(runtime):
    if runtime in LEGACY:
        return None
    if not isinstance(runtime, str) or not _SLUG.fullmatch(runtime):
        raise ProviderError('unsupported owned native runtime: %s' % runtime)
    path = _catalog().get(runtime)
    if path is None:
        raise ProviderError('unsupported owned native runtime: %s' % runtime)
    with _LOAD_LOCK:
        return _load_provider(runtime, path)


def _load_provider(runtime, path):
    package_name = '_xsm_owned_native_' + hashlib.sha256(
        (str(path.parent) + ':' + str(id(ProviderError))).encode()).hexdigest()[:24]
    name = package_name + '.worker_provider'
    if name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(path.parent)]
        sys.modules[package_name] = package
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            sys.modules.pop(package_name, None)
            raise
    module = sys.modules[name]
    required = ('default_home', 'prepare', 'environment', 'argv', 'result')
    control = getattr(module, 'CONTROL_PROTOCOL', None)
    if (getattr(module, 'RUNTIME', None) != runtime or type(control) is not int or control != 1
            or any(not callable(getattr(module, field, None)) for field in required)):
        raise ProviderError('native worker provider contract differs from catalog')
    return module
