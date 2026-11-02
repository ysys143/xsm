"""Native public SDK subprocess; never interprets config or exports credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .worker_session import NativeSessionError, decode_reply


class NativeRpc:
    def __init__(self, node, native_cli, *, cwd, env):
        if any(not isinstance(path, str) or not os.path.isabs(path) for path in (node, native_cli, cwd)):
            raise NativeSessionError('absolute native runtime paths required')
        self.command = [node, str(Path(__file__).with_name('worker_rpc.mjs')), native_cli]
        self.cwd, self.env = cwd, dict(env)
        # The private owner capability belongs only to the ordered frontend.
        self.env.pop('XSM_OWNED_CONTROL_FD', None)
        self.env.pop('XSM_WORKER', None)

    def __call__(self, method, params):
        payload = json.dumps({'method': method, 'params': params}, ensure_ascii=False, allow_nan=False)
        try:
            result = subprocess.run(self.command, input=payload, cwd=self.cwd, env=self.env,
                                    capture_output=True, text=True, timeout=50)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise NativeSessionError('native RPC transport failed; execution may be uncertain') from error
        if result.returncode:
            raise NativeSessionError('native RPC refused; inspect native state before recovery')
        return decode_reply(result.stdout)
