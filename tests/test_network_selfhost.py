"""Actual product CLI/services through an owned official localhost iroh relay.

Opt in with XSM_TEST_RELAY_BINARY (an already-built official iroh-relay).
No downloads, installation, mock relay, global firewall, trust-store changes,
or certificate-verification overrides are performed by this test.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from tests import test_network_service as core
from tests.test_network_service import CANARY, REPO, ServiceNode, process_table


UDP_PROFILE = '(version 1)(allow default)(deny network-outbound (remote udp "*:*"))'


class RelayNode(ServiceNode):
    def start(self):
        self.case.assertTrue(self.process is None or self.process.poll() is not None)
        number = len(self.runs)
        paths = [self.home / ("relay-service-%d.%s" % (number, suffix))
                 for suffix in ("stdout", "stderr")]
        descriptors = [os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) for path in paths]
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-B", "-m", "xsm.network", "serve"],
                cwd=REPO, env=self.env, stdin=subprocess.DEVNULL,
                stdout=descriptors[0], stderr=descriptors[1], start_new_session=True)
        finally:
            for descriptor in descriptors:
                os.close(descriptor)
        self.runs.append((self.process, *paths))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.case.assertIsNone(self.process.poll(), "owned service exited before relay ready")
            try:
                response = self.rpc({"op": "status"})
                if response.get("ok"):
                    self.status = response["result"]
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.025)
        else:
            self.case.fail("owned product service did not become ready")
        self.sidecar_pid = self.status["engine_pid"]
        parent, command = process_table()[self.sidecar_pid]
        self.case.assertEqual(parent, self.process.pid)
        self.case.assertEqual(Path(command).name, "xsm-net")
        self.case.assertEqual(self.status["transport"]["relay_mode"], "custom")
        self.case.assertTrue(self.status["transport"]["bound_addresses"])
        self.case.assertTrue(any(
            value.get("Relay", "").rstrip("/") == self.case.relay_url
            for value in self.status["address"].get("addrs", [])),
            "configured custom relay missing from initial public address")
        self.case.evidence["product_starts"].append({
            "name": self.name, "service_pid": self.process.pid,
            "engine_pid": self.sidecar_pid, "ready": self.status})
        return self


class NativeSelfHostedRelayTests(unittest.TestCase):
    # Reuse only helper methods; do not inherit/repeat the eight core tests.
    assert_no_secrets = core.NativeNetworkServiceTests.assert_no_secrets
    initialize = core.NativeNetworkServiceTests.initialize
    invite = core.NativeNetworkServiceTests.invite
    members = core.NativeNetworkServiceTests.members
    ping = core.NativeNetworkServiceTests.ping

    def setUp(self):
        relay = os.environ.get("XSM_TEST_RELAY_BINARY")
        if not relay or not Path(relay).is_file():
            self.skipTest("official_relay_binary_missing: explicit local opt-in required")
        if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("macos_process_local_udp_profile_required")
        native = Path(os.environ.get("XSM_TEST_NET_BINARY", str(REPO / "native/xsm-net/target/debug/xsm-net")))
        if not native.is_file():
            self.skipTest("native_debug_binary_missing")
        temporary = tempfile.TemporaryDirectory(prefix="xsrelay-", dir="/private/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.temp_dir = self.root / "tmp"
        self.temp_dir.mkdir(mode=0o700)
        self.outputs, self.secrets = [], [CANARY]
        self.evidence = {"scope": "actual-product-local-selfhost",
                         "product_starts": [], "path_snapshots": [],
                         "native_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
                         "native_source_binary": str(native),
                         "native_transport_source_sha256": hashlib.sha256(
                             (REPO / "native/xsm-net/src/transport.rs").read_bytes()).hexdigest(),
                         "official_relay_sha256": hashlib.sha256(Path(relay).read_bytes()).hexdigest(),
                         "udp_profile": UDP_PROFILE, "user_session_signals": 0}
        self.evidence["source_before"] = {
            name: hashlib.sha256((REPO / "xsm" / name).read_bytes()).hexdigest()
            for name in ("network.py", "network_transport.py", "network_membership.py", "cli.py")}
        self.addCleanup(self.save_evidence)
        self.check_udp_profile()
        binary_dir = self.root / "bin"
        binary_dir.mkdir(mode=0o700)
        copied_native = binary_dir / "xsm-net"
        shutil.copyfile(native, copied_native)
        copied_native.chmod(0o700)
        wrapper = binary_dir / "xsm-net-udp-blocked"
        wrapper.write_text("#!/bin/sh\nexec /usr/bin/sandbox-exec -p %s %s \"$@\"\n" %
                           (shlex.quote(UDP_PROFILE), shlex.quote(str(copied_native))))
        wrapper.chmod(0o700)
        self.binary = str(wrapper)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as available:
            available.bind(("127.0.0.1", 0))
            self.relay_port = available.getsockname()[1]
        self.relay_url = "http://127.0.0.1:%d" % self.relay_port
        self.evidence["relay_url"] = self.relay_url
        config = self.root / "relay.toml"
        config.write_text('http_bind_addr = "127.0.0.1:%d"\nenable_metrics = false\n'
                          'enable_quic_addr_discovery = false\naccess = "everyone"\n' % self.relay_port)
        config.chmod(0o600)
        self.relay_log = self.root / "official-relay.stderr"
        relay_fd = os.open(self.relay_log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        relay_env = {k: v for k, v in os.environ.items() if not k.startswith("IROH_")}
        relay_env.update(HOME=str(self.root), TMPDIR=str(self.temp_dir), RUST_LOG="iroh_relay=info")
        try:
            self.relay = subprocess.Popen([relay, "--config-path", str(config), "--dev"],
                                           cwd=self.root, env=relay_env, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.DEVNULL, stderr=relay_fd,
                                           start_new_session=True)
        finally:
            os.close(relay_fd)
        self.evidence["official_relay_pid"] = self.relay.pid
        self.addCleanup(self.stop_relay)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            self.assertIsNone(self.relay.poll(), "owned official relay exited")
            try:
                with socket.create_connection(("127.0.0.1", self.relay_port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.025)
        else:
            self.fail("owned official relay did not listen")
        self.a, self.b = self.node("a"), self.node("b")

    def check_udp_profile(self):
        # A live positive/negative control proves that this exact OS profile
        # prevents UDP egress. Only this freshly spawned probe is sandboxed.
        program = """import json,socket,sys
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
try:
 s.sendto(b'private-udp-control',('127.0.0.1',int(sys.argv[1])))
 print(json.dumps({'blocked':False}))
except PermissionError:
 print(json.dumps({'blocked':True}))
"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(0.2)
            command = [sys.executable, "-c", program, str(receiver.getsockname()[1])]
            control = subprocess.run(command, capture_output=True, text=True, timeout=3)
            self.assertFalse(json.loads(control.stdout)["blocked"])
            self.assertEqual(receiver.recv(128), b"private-udp-control")
            blocked = subprocess.run(["/usr/bin/sandbox-exec", "-p", UDP_PROFILE, *command],
                                     capture_output=True, text=True, timeout=3)
            self.assertTrue(json.loads(blocked.stdout)["blocked"])
            with self.assertRaises(socket.timeout):
                receiver.recv(128)
        self.evidence["udp_egress_controls"] = {"unrestricted_delivered": True,
                                               "same_profile_denied": True}

    def node(self, name):
        node = RelayNode(self, name)
        self.addCleanup(node.cleanup)
        node.cli("configure", "--relay", self.relay_url)
        return node.start()

    def check_relay_path(self, node):
        status = node.cli("status")
        route = status["last_transport"]
        self.assertEqual(route["path"], "relay")
        self.assertEqual(route["selected"], "relay")
        self.assertEqual(route["relay_url"].rstrip("/"), self.relay_url)
        self.assertFalse(any(p["kind"] == "direct" and p["selected"] for p in route["paths"]))
        self.evidence["path_snapshots"].append({"name": node.name, "status": status})

    def stop_relay(self):
        if self.relay.poll() is None:
            self.relay.send_signal(signal.SIGINT)
            try:
                self.relay.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.relay.kill()
                self.relay.wait(timeout=2)
        self.assertEqual(self.relay.returncode, 0)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            self.assertNotEqual(connection.connect_ex(("127.0.0.1", self.relay_port)), 0)
        starts = self.evidence["product_starts"]
        pids = {self.relay.pid} | {row[key] for row in starts for key in ("service_pid", "engine_pid")}
        remaining = sorted(pids.intersection(process_table()))
        self.evidence["cleanup"] = {"remaining_owned_pids": remaining,
                                    "relay_listener_closed": True}
        self.assertEqual(remaining, [])

    def save_evidence(self):
        self.evidence["source_after"] = {
            name: hashlib.sha256((REPO / "xsm" / name).read_bytes()).hexdigest()
            for name in self.evidence["source_before"]}
        self.evidence["sources_unchanged_during_run"] = (
            self.evidence["source_before"] == self.evidence["source_after"])
        self.evidence["public_cli_outputs"] = self.outputs
        raw = json.dumps(self.evidence, indent=2)
        self.assert_no_secrets(raw)
        destination = os.environ.get("XSM_TEST_RELAY_EVIDENCE")
        if destination:
            path = Path(destination)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(raw)
            if hasattr(self, "relay_log") and self.relay_log.exists():
                relay_raw = self.relay_log.read_text(errors="replace")
                self.assert_no_secrets(relay_raw)
                relay_path = path.with_name(path.stem + "-official-relay.stderr")
                descriptor = os.open(relay_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(relay_raw)

    def test_existing_product_cli_membership_rpc_restart_over_owned_relay(self):
        network = self.initialize(self.a, "bounded-product-selfhost")
        path, _ = self.invite(self.a)
        joined = self.b.cli("join", "--ticket-stdin", "--machine-name", self.b.name,
                            input=path.read_text())
        self.assertEqual(joined["network"]["network_id"], network)
        expected = {self.a.identity: "active", self.b.identity: "active"}
        self.assertEqual(self.members(self.a), expected)
        self.assertEqual(self.members(self.b), expected)
        for sender, receiver in ((self.a, self.b), (self.b, self.a)):
            self.ping(sender, receiver)
            self.check_relay_path(sender)
            self.check_relay_path(receiver)
        original = self.b.identity
        self.b.stop()
        self.b.start()
        self.assertEqual(self.b.identity, original)
        self.assertEqual(self.members(self.b), expected)
        self.ping(self.b, self.a)
        self.check_relay_path(self.b)
        self.check_relay_path(self.a)
        self.evidence["product_selfhost_passed"] = True
        self.evidence["product_ip_transports_removed"] = False
        self.evidence["product_udp_egress_denied"] = True
        self.evidence["certificate_verification_override"] = False


if __name__ == "__main__":
    unittest.main()
