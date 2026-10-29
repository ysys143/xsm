"""JSONL supervision tests; native QUIC tests are a separate, optional class."""
import base64
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest
from unittest import mock

from xsm import network_transport as transport


NODE = "a" * 64
PEER = "b" * 64
SECRET = "RAW-BODY-KEY-TICKET-STDERR-MUST-NOT-LEAK"
REPO = Path(__file__).resolve().parent.parent

# Kept in this test file so fixture installation changes no native artifacts.
FAKE_ENGINE = r'''
import base64, json, os, pathlib, signal, subprocess, sys, threading, time
args = sys.argv[1:]
root = pathlib.Path(args[args.index('--state-dir') + 1])
mode = root.name
root.joinpath('arguments.json').write_text(json.dumps(args))
node, peer = 'a' * 64, 'b' * 64
secret = 'RAW-BODY-KEY-TICKET-STDERR-MUST-NOT-LEAK'
lock = threading.Lock()
def send(event):
    with lock:
        print(json.dumps(event, separators=(',', ':')), flush=True)
def raw(value):
    with lock:
        sys.stdout.buffer.write(value)
        sys.stdout.buffer.flush()
def ready():
    send({'event':'ready', 'endpoint_id':node, 'address':{'id':node},
          'requested_port':int(args[args.index('--port') + 1]),
          'bound_addresses':['127.0.0.1:12345'], 'port_fallback':False})
if mode == 'no-ready':
    time.sleep(60)
if mode == 'startup-exit':
    sys.stderr.write(secret)
    sys.exit(17)
if mode == 'bad-ready':
    send({'event':'ready', 'endpoint_id':node, 'address':{}})
    time.sleep(60)
if mode == 'stubborn':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if mode == 'descendant':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    root.joinpath('child.pid').write_text(str(child.pid))
ready()
if mode == 'stderr-flood':
    sys.stderr.write(secret * 100000)
    sys.stderr.flush()
if mode == 'no-read':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(60)
waiting = {}
incoming_counter = 0
def response(command):
    global incoming_counter
    op = command['op']
    identifier = command.get('id')
    body = command.get('body', {})
    if op == 'shutdown':
        if mode == 'stubborn':
            return
        os._exit(0)
    if op == 'respond':
        original = waiting.pop(identifier)
        if mode == 'expired-incoming':
            send({'event':'error', 'id':identifier, 'code':'unknown_request'})
            send({'event':'response', 'id':original, 'origin':peer, 'body':{'expired':True}})
            return
        send({'event':'response', 'id':original, 'origin':peer, 'body':body})
        if mode == 'path-events':
            send({'event':'path', 'direction':'incoming', 'request_id':identifier,
                  'origin':peer, 'transport':{'path':'direct', 'body':secret, 'ticket':secret}})
        return
    if op == 'sign':
        data = base64.b64decode(command['data'])
        signature = data.hex().ljust(128, '0')[:128]
        send({'event':'result', 'id':identifier, 'signature':signature})
        return
    if op == 'verify':
        data = base64.b64decode(command['data'])
        valid = command['signature'] == data.hex().ljust(128, '0')[:128]
        send({'event':'result', 'id':identifier, 'valid':valid})
        return
    if op == 'address':
        send({'event':'result', 'id':identifier, 'address':{'id':node, 'updated':True}})
        return
    action = body.get('action', 'echo') if isinstance(body, dict) else 'echo'
    if action == 'wait':
        return
    if action == 'delay':
        time.sleep(body['seconds'])
    if action == 'exit':
        sys.stderr.write(secret)
        os._exit(17)
    if action == 'exit-descendant':
        os._exit(17)
    if action == 'stdout-eof':
        os.close(1)
        time.sleep(60)
        return
    if action == 'invalid':
        raw(base64.b64decode(body['bytes']))
        return
    if action == 'partial-eof':
        raw(b'{"ticket":"' + secret.encode())
        os.close(1)
        time.sleep(60)
        return
    if action == 'oversized':
        raw(b'x' * (12 * 1024 * 1024 + 1))
        time.sleep(60)
        return
    if action == 'incoming' or action == 'duplicate-incoming':
        incoming_counter += 1
        key = 'in-%d' % incoming_counter
        waiting[key] = identifier
        event = {'event':'request', 'request_id':key, 'origin':peer,
                 'body':{'origin':'forged', 'nonce':body.get('nonce')}}
        send(event)
        if action == 'duplicate-incoming':
            send(event)
        return
    if action == 'bad-origin':
        send({'event':'response', 'id':identifier, 'body':{'origin':peer}})
        return
    if action == 'error':
        send({'event':'error', 'id':identifier, 'code':body['code'], 'detail':secret})
        return
    if action == 'duplicate-ready':
        ready()
        return
    if action == 'unknown-id':
        send({'event':'result', 'id':'unknown', 'valid':True})
        return
    if action == 'wrong-kind':
        send({'event':'result', 'id':identifier, 'valid':True})
        return
    event = {'event':'response', 'id':identifier, 'origin':peer, 'body':body}
    send(event)
    if action == 'duplicate':
        send(event)
for line in sys.stdin:
    command = json.loads(line)
    threading.Thread(target=response, args=(command,), daemon=True).start()
'''


class FakeEngineTests(unittest.TestCase):
    def setUp(self):
        global transport
        from xsm import network_transport as transport
        self.tmp = tempfile.TemporaryDirectory(prefix="xsm-sidecar-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = self.root / "fake-engine"
        self.engine.write_text("#!%s\n%s" % (sys.executable, FAKE_ENGINE), encoding="utf-8")
        self.engine.chmod(0o700)

    def sidecar(self, mode="normal", start=True, **kwargs):
        sidecar = transport.Sidecar(self.root / mode, binary=self.engine, **kwargs)
        self.addCleanup(sidecar.close)
        if start:
            sidecar.start(timeout=3)
        return sidecar

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(transport.SidecarError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        formatted = "".join(traceback.format_exception(
            type(caught.exception), caught.exception, caught.exception.__traceback__))
        self.assertNotIn(SECRET, formatted)
        return caught.exception

    def wait_stopped(self, sidecar):
        self.assertTrue(sidecar._cleanup_done.wait(3), "cleanup did not complete")
        self.assertIsNotNone(sidecar._process.poll(), "engine was left running")

    def test_import_and_construction_have_no_process_or_state_side_effects(self):
        with mock.patch.object(subprocess, "Popen") as popen:
            importlib.reload(transport)
            sidecar = transport.Sidecar(self.root / "uncreated", binary=self.engine)
            self.assertIsNone(sidecar.endpoint_id)
            self.assertIsNone(sidecar.address)
            self.assertFalse(sidecar.state_dir.exists())
            popen.assert_not_called()
            sidecar.close()

    def test_explicit_binary_and_environment_override_precedence(self):
        with mock.patch.dict(os.environ, {"XSM_NET_BINARY": str(self.root / "missing")}):
            self.assertEqual(transport.find_binary(self.engine), str(self.engine))
            self.assert_code("binary_missing", transport.find_binary)
        with mock.patch.dict(os.environ, {"XSM_NET_BINARY": str(self.engine)}):
            self.assertEqual(transport.find_binary(), str(self.engine))
            self.assert_code("binary_missing", transport.find_binary, self.root / "missing")

    def test_repository_release_then_debug_lookup_without_path_search(self):
        fake_module = self.root / "repository" / "xsm" / "network_transport.py"
        target = fake_module.parent.parent / "native" / "xsm-net" / "target"
        for mode in ("release", "debug"):
            binary = target / mode / "xsm-net"
            binary.parent.mkdir(parents=True)
            binary.write_text("fixture")
            binary.chmod(0o700)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(transport, "__file__", str(fake_module)):
            self.assertEqual(transport.find_binary(), str((target / "release" / "xsm-net").resolve()))
            (target / "release" / "xsm-net").unlink()
            self.assertEqual(transport.find_binary(), str((target / "debug" / "xsm-net").resolve()))
            (target / "debug" / "xsm-net").unlink()
            self.assert_code("binary_missing", transport.find_binary)

    def test_missing_or_nonexecutable_binary_does_not_create_state_or_chmod(self):
        missing = self.sidecar("uncreated", start=False)
        missing.binary = self.root / SECRET
        self.assert_code("binary_missing", missing.start)
        self.assertFalse(missing.state_dir.exists())
        self.engine.chmod(0o600)
        self.assert_code("binary_not_executable", transport.find_binary, self.engine)
        self.assertEqual(stat.S_IMODE(self.engine.stat().st_mode), 0o600)

    def test_spawn_and_binary_inspection_errors_are_redacted(self):
        sidecar = self.sidecar("spawn-failure", start=False)
        with mock.patch.object(subprocess, "Popen", side_effect=OSError(SECRET)):
            self.assert_code("spawn_failed", sidecar.start)
        with mock.patch.object(Path, "is_file", side_effect=OSError(SECRET)):
            self.assert_code("binary_unavailable", transport.find_binary, self.engine)

    def test_private_state_ancestors_without_global_permission_changes(self):
        parent_mode = stat.S_IMODE(self.root.stat().st_mode)
        sidecar = self.sidecar("new/inner/normal")
        for path in (self.root / "new", self.root / "new/inner", sidecar.state_dir):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), parent_mode)

    def test_unsafe_existing_state_and_symlink_are_rejected(self):
        unsafe = self.root / "unsafe"
        unsafe.mkdir(mode=0o755)
        sidecar = self.sidecar("unsafe", start=False)
        self.assert_code("state_permissions", sidecar.start)
        self.assertEqual(stat.S_IMODE(unsafe.stat().st_mode), 0o755)
        (self.root / "linked").symlink_to(unsafe, target_is_directory=True)
        self.assert_code("state_permissions", self.sidecar("linked", start=False).start)

    def test_ready_and_arguments_and_idempotent_start(self):
        sidecar = self.sidecar(port=4444, relay="off", direct_addresses=("127.0.0.1:4444", "[::1]:4444"))
        ready = sidecar.start()
        pid = sidecar._process.pid
        self.assertEqual(sidecar.endpoint_id, NODE)
        self.assertEqual(sidecar.address, {"id": NODE})
        args = json.loads((sidecar.state_dir / "arguments.json").read_text())
        self.assertEqual(args, ["serve", "--state-dir", str(sidecar.state_dir), "--port", "4444",
                                "--relay", "off", "--direct-address", "127.0.0.1:4444", "--direct-address", "[::1]:4444"])
        ready["address"]["id"] = "changed"
        self.assertEqual(sidecar.start()["endpoint_id"], NODE)
        self.assertEqual(sidecar.address["id"], NODE)
        self.assertEqual(sidecar._process.pid, pid)

    def test_default_relay_omits_relay_flag(self):
        sidecar = self.sidecar()
        self.assertNotIn("--relay", json.loads((sidecar.state_dir / "arguments.json").read_text()))
        address = sidecar.call("address")
        self.assertTrue(address["address"]["updated"])
        self.assertEqual(sidecar.address, address["address"])

    def test_sign_verify_bytes_callbacks(self):
        sidecar = self.sidecar()
        signature = sidecar.sign(b"\x00\xffmembership")
        self.assertTrue(sidecar.verify(NODE, b"\x00\xffmembership", signature))
        self.assertFalse(sidecar.verify(NODE, b"altered", signature))
        self.assert_code("invalid_data", sidecar.sign, SECRET)
        self.assert_code("invalid_data", sidecar.verify, NODE, SECRET, signature)

    def test_many_calls_are_correlated_out_of_order(self):
        sidecar = self.sidecar()
        def request(number):
            body = {"action": "delay", "seconds": (23 - number) * 0.002, "number": number}
            return sidecar.request({"id": PEER}, body, timeout=3)
        with ThreadPoolExecutor(max_workers=24) as executor:
            results = list(executor.map(request, range(24)))
        self.assertEqual([result["body"]["number"] for result in results], list(range(24)))
        self.assertTrue(all(result["origin"] == PEER for result in results))
        self.assertEqual(sidecar._pending, {})

    def test_incoming_handler_can_sign_verify_and_request(self):
        sidecar = self.sidecar()
        seen = []
        def callback(origin, body):
            seen.append((origin, body["origin"]))
            signature = sidecar.sign(b"membership", timeout=2)
            self.assertTrue(sidecar.verify(NODE, b"membership", signature, timeout=2))
            inner = sidecar.request({"id": PEER}, {"nested": True}, timeout=2)
            return {"nonce": body["nonce"], "nested": inner["body"]}
        sidecar.set_request_handler(callback)
        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(lambda n: sidecar.request({"id": PEER}, {"action": "incoming", "nonce": n}, timeout=4), range(16)))
        self.assertEqual([r["body"]["nonce"] for r in results], list(range(16)))
        self.assertEqual(seen, [(PEER, "forged")] * 16)
        self.assertTrue(all(r["body"]["nested"] == {"nested": True} for r in results))

    def test_handler_failure_and_absence_return_fixed_errors(self):
        sidecar = self.sidecar()
        absent = sidecar.request({}, {"action": "incoming"})
        self.assertEqual(absent["body"], {"error": {"code": "handler_unavailable"}})
        def fail(origin, body):
            raise RuntimeError(SECRET)
        sidecar.set_request_handler(fail)
        result = sidecar.request({}, {"action": "incoming"})
        self.assertEqual(result["body"], {"error": {"code": "handler_failed"}})
        sidecar.set_request_handler(lambda *_: object())
        self.assertEqual(sidecar.request({}, {"action": "incoming"})["body"], result["body"])

    def test_expired_incoming_response_does_not_poison_other_calls(self):
        sidecar = self.sidecar("expired-incoming")
        sidecar.set_request_handler(lambda *_: {"ok": True})
        self.assertEqual(sidecar.request({}, {"action": "incoming"})["body"], {"expired": True})
        self.assertIn("address", sidecar.call("address"))

    def test_native_path_diagnostic_extension_preserves_rpc_contract(self):
        sidecar = self.sidecar("path-events")
        sidecar.set_request_handler(lambda *_: {"ok": True})
        result = sidecar.request({}, {"action": "incoming"})
        self.assertEqual(set(result), {"origin", "body"})
        self.assertIn("address", sidecar.call("address"))
        self.assertEqual(sidecar.last_transport, {"path": "direct"})
        snapshot = sidecar.last_transport
        snapshot["path"] = "changed"
        self.assertEqual(sidecar.last_transport, {"path": "direct"})

    def test_handler_can_close_without_waiting_on_its_own_executor(self):
        sidecar = self.sidecar()
        finished = threading.Event()
        def callback(*_):
            sidecar.close()
            finished.set()
            return {"ok": True}
        sidecar.set_request_handler(callback)
        self.assert_code("closed", sidecar.request, {}, {"action": "incoming"}, timeout=3)
        self.assertTrue(finished.wait(3))
        self.wait_stopped(sidecar)

    def test_slow_handler_does_not_delay_independent_outbound_call(self):
        sidecar = self.sidecar()
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        def callback(*_):
            entered.set()
            release.wait(3)
            return {"ok": True}
        sidecar.set_request_handler(callback)
        with ThreadPoolExecutor(max_workers=1) as executor:
            incoming = executor.submit(sidecar.request, {}, {"action": "incoming"}, timeout=3)
            self.assertTrue(entered.wait(2))
            try:
                self.assertIn("address", sidecar.call("address", timeout=0.5))
            finally:
                release.set()
            self.assertEqual(incoming.result()["body"], {"ok": True})

    def test_timeout_removes_pending_and_late_reply_does_not_poison_next_call(self):
        sidecar = self.sidecar()
        self.assert_code("timeout", sidecar.request, {}, {"action": "delay", "seconds": 0.15}, timeout=0.025)
        self.assertEqual(sidecar._pending, {})
        time.sleep(0.2)
        self.assertTrue(sidecar.call("address")["address"]["updated"])

    def test_timeout_also_covers_blocked_stdin(self):
        sidecar = self.sidecar("no-read")
        started = time.monotonic()
        self.assert_code("timeout", sidecar.request, {}, "x" * (1024 * 1024), timeout=0.1)
        self.assertLess(time.monotonic() - started, 1)
        sidecar.close()
        self.wait_stopped(sidecar)

    def test_stderr_is_discarded_and_cannot_block_engine(self):
        sidecar = self.sidecar("stderr-flood")
        self.assertEqual(sidecar.request({}, {"ok": True}, timeout=2)["body"], {"ok": True})

    def test_process_exit_fails_all_pending_without_payload_or_stderr(self):
        sidecar = self.sidecar()
        with ThreadPoolExecutor(max_workers=5) as executor:
            waiting = [executor.submit(sidecar.request, {}, {"action": "wait", "secret": SECRET}, timeout=3) for _ in range(4)]
            self.assert_code("process_exited", sidecar.request, {}, {"action": "exit"}, timeout=3)
            for future in waiting:
                self.assert_code("process_exited", future.result)
        self.wait_stopped(sidecar)

    def test_stdout_eof_terminates_a_still_running_process(self):
        sidecar = self.sidecar()
        self.assert_code("process_exited", sidecar.request, {}, {"action": "stdout-eof"}, timeout=2)
        self.wait_stopped(sidecar)

    def test_partial_line_at_eof_is_rejected_and_redacted(self):
        sidecar = self.sidecar()
        self.assert_code("invalid_stdout", sidecar.request, {}, {"action": "partial-eof"}, timeout=2)
        self.wait_stopped(sidecar)

    def test_startup_exit_timeout_and_invalid_ready_are_reaped(self):
        for mode, code in (("startup-exit", "process_exited"), ("no-ready", "start_timeout"), ("bad-ready", "invalid_stdout")):
            with self.subTest(mode=mode):
                sidecar = self.sidecar(mode, start=False)
                self.assert_code(code, sidecar.start, timeout=0.2 if mode == "no-ready" else 2)
                self.wait_stopped(sidecar)

    def test_malformed_stdout_never_leaks_raw_line(self):
        invalid = [b'not-json-' + SECRET.encode() + b'\n', b'[]\n', b'\xff\n',
                   b'{"event":"result","event":"request"}\n', b'{"event":NaN}\n',
                   b'{"event":"unknown","ticket":"' + SECRET.encode() + b'"}\n']
        for index, raw in enumerate(invalid):
            with self.subTest(raw=index):
                sidecar = self.sidecar("invalid-%d" % index)
                body = {"action": "invalid", "bytes": base64.b64encode(raw).decode()}
                self.assert_code("invalid_stdout", sidecar.request, {}, body, timeout=2)
                self.wait_stopped(sidecar)

    def test_line_bound_is_enforced_without_waiting_for_newline(self):
        sidecar = self.sidecar()
        self.assert_code("ipc_too_large", sidecar.request, {}, {"action": "oversized"}, timeout=3)
        self.wait_stopped(sidecar)

    def test_outbound_frame_json_and_ipc_bounds_leave_engine_usable(self):
        sidecar = self.sidecar()
        self.assert_code("frame_too_large", sidecar.request, {}, "x" * transport.MAX_FRAME)
        self.assert_code("ipc_too_large", sidecar.call, "sign", data="x" * transport.MAX_IPC_LINE)
        self.assert_code("invalid_json", sidecar.request, {}, {"secret": SECRET, "value": float('nan')})
        self.assert_code("invalid_json", sidecar.request, {}, {"value": object()})
        self.assertEqual(sidecar._pending, {})
        self.assertIn("address", sidecar.call("address"))

    def test_duplicate_incoming_response_and_ready_ids_stop_engine(self):
        for index, action in enumerate(("duplicate-incoming", "duplicate", "duplicate-ready")):
            with self.subTest(action=action):
                sidecar = self.sidecar("duplicate-%d" % index)
                sidecar.set_request_handler(lambda *_: {"ok": True})
                try:
                    sidecar.request({}, {"action": action}, timeout=2)
                except transport.SidecarError as exc:
                    self.assertEqual(exc.code, "duplicate_id")
                self.wait_stopped(sidecar)
                self.assert_code("duplicate_id", sidecar.call, "address")

    def test_origin_is_required_from_engine_and_never_from_body(self):
        sidecar = self.sidecar()
        result = sidecar.request({}, {"origin": "forged"})
        self.assertEqual(result["origin"], PEER)
        self.assertEqual(result["body"]["origin"], "forged")
        self.assert_code("invalid_stdout", sidecar.request, {}, {"action": "bad-origin"})
        self.wait_stopped(sidecar)

    def test_unknown_ids_wrong_result_shapes_and_unknown_errors(self):
        for index, action in enumerate(("unknown-id", "wrong-kind")):
            sidecar = self.sidecar("bad-result-%d" % index)
            self.assert_code("unknown_id" if action == "unknown-id" else "invalid_stdout", sidecar.request, {}, {"action": action})
            self.wait_stopped(sidecar)
        sidecar = self.sidecar()
        self.assert_code("engine_error", sidecar.request, {}, {"action": "error", "code": SECRET})
        self.assert_code("connect_failed", sidecar.request, {}, {"action": "error", "code": "connect_failed"})
        self.assertIn("address", sidecar.call("address"))

    def test_close_is_idempotent_and_kills_uncooperative_engine(self):
        sidecar = self.sidecar("stubborn")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(sidecar.request, {}, {"action": "wait"}, timeout=3)
            time.sleep(0.03)
            sidecar.close()
            self.assert_code("closed", future.result)
        self.wait_stopped(sidecar)
        sidecar.close()
        self.assert_code("closed", sidecar.start)
        self.assertFalse(sidecar._reader.is_alive())
        self.assertFalse(sidecar._writer.is_alive())

    def test_exiting_parent_cannot_leave_descendant_holding_stdout(self):
        sidecar = self.sidecar("descendant")
        child_pid = int((sidecar.state_dir / "child.pid").read_text())
        self.addCleanup(self._kill_if_alive, child_pid)
        self.assert_code("process_exited", sidecar.request, {}, {"action": "exit-descendant"}, timeout=2)
        self.wait_stopped(sidecar)
        result = subprocess.run(["ps", "-o", "stat=", "-p", str(child_pid)], capture_output=True, text=True)
        self.assertTrue(not result.stdout.strip() or result.stdout.strip().startswith('Z'), "descendant survived cleanup")

    @staticmethod
    def _kill_if_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def test_invalid_arguments_and_unstarted_calls_are_fixed_errors(self):
        for timeout in (0, -1, float('inf'), float('nan'), True, SECRET, 10 ** 1000):
            sidecar = self.sidecar("unstarted", start=False)
            self.assert_code("invalid_timeout", sidecar.start, timeout=timeout)
        for port in (-1, 65536, True, SECRET):
            self.assert_code("invalid_port", transport.Sidecar, self.root / 'unused', port=port)
        sidecar = self.sidecar("unstarted", start=False)
        self.assert_code("not_started", sidecar.call, "address")
        self.assert_code("invalid_command", sidecar.call, "shutdown")
        self.assert_code("invalid_command", sidecar.call, "address", id=SECRET)

    def test_context_manager_always_reaps_on_application_error(self):
        sidecar = self.sidecar(start=False)
        with self.assertRaisesRegex(ValueError, "application_failure"):
            with sidecar:
                raise ValueError("application_failure")
        self.wait_stopped(sidecar)
        self.assert_code("closed", sidecar.call, "address")


def _native_binary():
    try:
        return transport.find_binary()
    except transport.SidecarError:
        return None


class NativeEngineTests(unittest.TestCase):
    """Real same-host QUIC; does not claim a two-machine or relay journey."""

    def setUp(self):
        global transport
        from xsm import network_transport as transport
        binary = _native_binary()
        if binary is None:
            self.skipTest("native_binary_missing")
        self.tmp = tempfile.TemporaryDirectory(prefix="xsm-native-")
        self.addCleanup(self.tmp.cleanup)
        self.a = transport.Sidecar(Path(self.tmp.name) / "a", relay="off", binary=binary)
        self.b = transport.Sidecar(Path(self.tmp.name) / "b", relay="off", binary=binary)
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)
        self.a.start(timeout=10)
        self.b.start(timeout=10)

    def test_actual_rpc_callback_sign_verify_and_authenticated_origins(self):
        observed = []
        def callback(origin, body):
            observed.append(origin)
            signature = self.b.sign(b"membership\x00\xff")
            return {"echo": body, "signature": signature}
        self.b.set_request_handler(callback)
        result = self.a.request(self.b.address, {"origin": "forged", "hello": "QUIC"}, timeout=10)
        self.assertEqual(observed, [self.a.endpoint_id])
        self.assertEqual(result["origin"], self.b.endpoint_id)
        self.assertEqual(result["body"]["echo"], {"origin": "forged", "hello": "QUIC"})
        signature = result["body"]["signature"]
        self.assertTrue(self.a.verify(self.b.endpoint_id, b"membership\x00\xff", signature))
        self.assertFalse(self.a.verify(self.b.endpoint_id, b"altered", signature))
        self.assertFalse(self.a.verify(self.a.endpoint_id, b"membership\x00\xff", signature))
        for sidecar in (self.a, self.b):
            self.assertEqual(stat.S_IMODE(sidecar.state_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((sidecar.state_dir / 'node.secret').stat().st_mode), 0o600)
        self.a.close()
        self.b.close()
        self.assertIsNotNone(self.a._process.poll())
        self.assertIsNotNone(self.b._process.poll())

    def test_actual_bidirectional_concurrent_rpc_and_key_persistence(self):
        self.a.set_request_handler(lambda origin, body: {"from": origin, "echo": body})
        self.b.set_request_handler(lambda origin, body: {"from": origin, "echo": body})
        def exchange(number):
            sender, receiver = (self.a, self.b) if number % 2 else (self.b, self.a)
            result = sender.request(receiver.address, {"number": number}, timeout=10)
            self.assertEqual(result["origin"], receiver.endpoint_id)
            self.assertEqual(result["body"], {"from": sender.endpoint_id, "echo": {"number": number}})
        # The native engine allows four concurrent streams per connection.
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(exchange, range(24)))
        identity = self.a.endpoint_id
        self.a.close()
        restarted = transport.Sidecar(self.a.state_dir, relay="off", binary=self.a.binary)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.start(timeout=10)["endpoint_id"], identity)


if __name__ == "__main__":
    unittest.main()
