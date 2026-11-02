"""Native CLI entrypoint with a private pre-turn identity observer.

The original CLI parses flags, checks startup consent, creates/resumes the native
session and runs the gateway turn. Only StreamJsonEmitter.bind_session is observed;
its synchronous return waits for the owned journal before the CLI starts the turn.
No model reply, native permission, route, session ID or tool list is synthesized.
"""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from xsm.native_worker_control import WorkerControlClient, ControlError


def main():
    control = WorkerControlClient.from_environment()
    # A shared gateway never inherits one client's worker label as global state.
    os.environ.pop('XSM_WORKER', None)
    from hermes_cli import stream_json
    from hermes_cli.gateway_client import GatewayClientError
    original = stream_json.StreamJsonEmitter

    class OwnedEmitter(original):
        def bind_session(self, session_id):
            try:
                control.bind(session_id)
            except ControlError:
                raise GatewayClientError('owned native context binding was refused') from None
            super().bind_session(session_id)

    stream_json.StreamJsonEmitter = OwnedEmitter
    try:
        from hermes_cli.main import main as native_main
        return native_main()
    finally:
        stream_json.StreamJsonEmitter = original
        control.close()


if __name__ == '__main__':
    raise SystemExit(main())
