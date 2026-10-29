"""Real Python services, public CLI, Ed25519 and QUIC on this host.

No mock transports or fixture signatures are used here. These tests require an
already-built xsm-net and never build/install it. They do not establish physical
machine, NAT, relay, deployment or account integration coverage.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest

from xsm.network_transport import Sidecar, SidecarError, find_binary


REPO = Path(__file__).resolve().parents[1]
CANARY = "SERVICE-RAW-ERROR-BODY-TICKET-MUST-NOT-APPEAR"
CLI_TIMEOUT = 8
RPC_TIMEOUT = 5


def process_table():
    """Read PID/parent/command names, never arbitrary process arguments."""
    result = subprocess.run(["ps", "-axo", "pid=,ppid=,comm="],
                            capture_output=True, text=True, timeout=3, check=True)
    rows = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3:
            rows[int(fields[0])] = (int(fields[1]), fields[2])
    return rows


class ServiceNode:
    """Own a foreground service and identify its actual native child."""

    def __init__(self, case, name):
        self.case, self.name = case, name
        self.home = case.root / name
        self.home.mkdir(mode=0o700)
        self.os_home = self.home / "os-home"
        self.os_home.mkdir(mode=0o700)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("XSM_", "CLAUDE_", "CODEX_", "ORCA_", "OTEL_"))
                    and k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        self.env.update(HOME=str(self.os_home), XSM_HOME=str(self.home),
                        XSM_TEMP=str(case.root), TMPDIR=str(case.temp_dir),
                        XDG_CONFIG_HOME=str(self.os_home / "config"),
                        CLAUDE_CONFIG_DIR=str(self.os_home / "claude"),
                        CODEX_HOME=str(self.os_home / "codex"),
                        PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1",
                        XSM_NET_BINARY=case.binary)
        digest = hashlib.sha256(os.path.realpath(self.home).encode()).hexdigest()[:24]
        self.socket = case.temp_dir / ("xsm-net-%d" % os.getuid()) / (digest + ".sock")
        self.process = None
        self.sidecar_pid = None
        self.status = None
        self.runs = []
        self.cli("configure", "--relay", "off", "--port", "0")

    def cli(self, *args, input=None, success=True):
        result = subprocess.run([sys.executable, "-B", "-m", "xsm", "network", *args],
                                cwd=REPO, env=self.env, input=input,
                                capture_output=True, text=True, timeout=CLI_TIMEOUT)
        self.case.outputs.append((result.stdout, result.stderr))
        self.case.assert_no_secrets(result.stdout + result.stderr)
        self.case.assertEqual(result.returncode, 0 if success else 4,
                              "public CLI exit mismatch: " + "/".join(args[:1]))
        self.case.assertEqual(result.stderr, "", "public CLI emitted stderr")
        try:
            value = json.loads(result.stdout)
        except ValueError:
            self.case.fail("public CLI did not emit a single JSON result")
        if not success:
            self.case.assertEqual(value.get("status"), "error")
        return value

    def rpc(self, request):
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(RPC_TIMEOUT)
            connection.connect(str(self.socket))
            connection.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
            with connection.makefile("rb") as stream:
                raw = stream.readline(8 * 1024 * 1024 + 2)
        self.case.assert_no_secrets(raw.decode())
        return json.loads(raw)

    def start(self):
        self.case.assertTrue(self.process is None or self.process.poll() is not None)
        number = len(self.runs)
        out_path, err_path = (self.home / ("service-%d.%s" % (number, suffix))
                              for suffix in ("stdout", "stderr"))
        with out_path.open("wb") as out, err_path.open("wb") as err:
            self.process = subprocess.Popen(
                [sys.executable, "-B", "-m", "xsm.network", "serve"],
                cwd=REPO, env=self.env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True)
        self.runs.append((self.process, out_path, err_path))
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.case.fail("owned Python service exited before ready")
            try:
                reply = self.rpc({"op": "status"})
                if reply.get("ok"):
                    self.status = reply["result"]
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.025)
        else:
            self.case.fail("owned Python service readiness timeout")
        children = [(pid, command) for pid, (parent, command) in process_table().items()
                    if parent == self.process.pid and Path(command).name == "xsm-net"]
        self.case.assertEqual(len(children), 1, "service must own exactly one Rust sidecar")
        self.sidecar_pid = children[0][0]
        self.case.assertIsNone(self.process.poll())
        self.case.assertTrue(self.socket.is_socket())
        self.case.assertEqual(stat.S_IMODE(self.socket.stat().st_mode), 0o600)
        self.case.assertEqual(stat.S_IMODE(self.socket.parent.stat().st_mode), 0o700)
        self.case.assertEqual(self.status["transport"]["relay_mode"], "off")
        self.case.assertEqual(self.cli("status")["endpoint_id"], self.identity)
        return self

    @property
    def identity(self):
        return self.status["endpoint_id"]

    @property
    def address(self):
        return self.status["address"]

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        self.case.assertEqual(self.cli("stop")["status"], "stopping")
        self.process.wait(timeout=4)
        self.case.assertEqual(self.process.returncode, 0, "service stop failed")
        self.case.assertNotIn(self.sidecar_pid, process_table(), "native child survived stop")
        self.case.assertFalse(self.socket.exists(), "control socket survived stop")
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(0.2)
            with self.case.assertRaises(OSError):
                connection.connect(str(self.socket))
        # Process exit alone is insufficient: the actual UDP listener must close.
        for address in self.status["transport"]["bound_addresses"]:
            if address.startswith("["):
                continue
            port = int(address.rsplit(":", 1)[1])
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
                listener.bind(("0.0.0.0", port))
        self.case.assertEqual(self.cli("status")["status"], "stopped")

    def cleanup(self):
        try:
            self.stop()
        finally:
            # Fallbacks target only our live Popen and its recorded direct child.
            if self.process is not None and self.process.poll() is None:
                table = process_table()
                children = [pid for pid, (parent, command) in table.items()
                            if parent == self.process.pid and Path(command).name == "xsm-net"]
                for pid in children:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                deadline = time.monotonic() + 0.5
                while children and time.monotonic() < deadline:
                    table = process_table()
                    children = [pid for pid in children if pid in table
                                and table[pid][0] == self.process.pid]
                    if children:
                        time.sleep(0.025)
                for pid in children:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            for process, out_path, err_path in self.runs:
                self.case.assertIsNotNone(process.poll(), "owned service remains alive")
                for path in (out_path, err_path):
                    raw = path.read_text(errors="replace")
                    self.case.assert_no_secrets(raw)
                    self.case.assertEqual(raw, "", "Python service wrote unexpected diagnostics")


class NativeNetworkServiceTests(unittest.TestCase):
    """Actual CLI/control/QUIC/membership tests; no unit signature fixtures."""

    def setUp(self):
        try:
            self.binary = find_binary()
        except SidecarError as exc:
            if exc.code == "binary_missing":
                self.skipTest("native_binary_missing: no automatic build or installation")
            raise
        # Short paths keep Unix socket names below the macOS AF_UNIX bound.
        self.temporary = tempfile.TemporaryDirectory(prefix="xsn-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.temp_dir = self.root / "tmp"
        self.temp_dir.mkdir(mode=0o700)
        self.secrets = [CANARY]
        self.outputs = []
        self.a, self.b = self.node("a"), self.node("b")

    def node(self, name):
        node = ServiceNode(self, name)
        self.addCleanup(node.cleanup)
        return node.start()

    def assert_no_secrets(self, text):
        for secret in self.secrets:
            if secret in text:
                self.fail("secret reflected in public output or service diagnostics")

    def initialize(self, node, name="service-team"):
        result = node.cli("init", name, "--machine-name", node.name)
        self.assertTrue(result["active"])
        return result["network"]["network_id"]

    def invite(self, node, once=False):
        args = ("invite", "--once", "--expires", "60") if once else ("invite",)
        result = node.cli(*args)
        path = Path(result["ticket_file"])
        self.assertTrue(path.is_relative_to(node.home / "network" / "invites"))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        ticket = json.loads(path.read_text())
        self.secrets.append(ticket["secret"])
        for out, err in self.outputs:
            self.assert_no_secrets(out + err)
        self.assertEqual(ticket["reusable"], not once)
        return path, ticket

    def join(self, node, path, success=True):
        return node.cli("join", "--ticket-file", str(path), "--machine-name", node.name, success=success)

    def members(self, node):
        return {row["endpoint_id"]: row["status"] for row in node.cli("members")["members"]}

    def state(self, node):
        files = list((node.home / "network" / "networks").glob("*/membership.json"))
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text())

    def private_ticket(self, name, ticket):
        path = self.root / (name + ".json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(ticket, stream)
        return path

    def ping(self, sender, receiver, success=True):
        result = sender.rpc({"op": "ping", "peer": receiver.address})
        self.assertIs(result["ok"], success)
        if success:
            self.assertEqual(result["result"]["endpoint_id"], receiver.identity)
        return result

    def probe(self):
        return self.owned_sidecar(self.root / "wire-probe")

    def admit_probe(self, probe, issuer):
        # Bootstrap a real TLS peer through the service's signed admission path.
        # Business RPC must never bypass the active-member check for a test.
        _, ticket = self.invite(issuer)
        response = probe.request(issuer.address, {
            "op": "join", "network_id": ticket["network_id"],
            "secret": ticket["secret"], "machine_name": "wire-probe",
            "address": probe.address}, timeout=RPC_TIMEOUT)
        self.assertEqual(response["origin"], issuer.identity)
        self.assertTrue(response["body"]["ok"])
        self.assertEqual(response["body"]["network_id"], ticket["network_id"])
        self.assertEqual(self.members(issuer)[probe.endpoint_id], "active")

    def owned_sidecar(self, directory):
        probe = Sidecar(directory, relay="off", binary=self.binary)
        def cleanup():
            probe.close()
            if probe._process is not None:
                self.assertIsNotNone(probe._process.poll(), "owned wire probe survived cleanup")
        self.addCleanup(cleanup)
        probe.start(timeout=5)
        return probe

    def test_public_cli_reusable_join_retry_and_third_device(self):
        network = self.initialize(self.a)
        path, _ = self.invite(self.a)
        self.assertEqual(self.join(self.b, path)["network"]["network_id"], network)
        before = self.state(self.a)
        self.join(self.b, path)
        self.assertEqual(self.state(self.a), before, "retry added a second admission")
        identity = self.b.identity
        self.b.stop()
        self.b.start()
        self.assertEqual(self.b.identity, identity)
        self.join(self.b, path)
        c = self.node("c")
        self.join(c, path)
        self.ping(self.b, self.a)
        expected = {node.identity: "active" for node in (self.a, self.b, c)}
        self.assertEqual(self.members(self.a), expected)
        self.assertEqual(self.members(c), expected)

    def test_one_time_response_loss_retry_restart_and_different_device_refusal(self):
        self.initialize(self.a)
        path, ticket = self.invite(self.a, once=True)
        # Really drop a local join response after sending the full request.
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(RPC_TIMEOUT)
            connection.connect(str(self.b.socket))
            request = {"op": "join", "ticket": ticket, "machine_name": self.b.name}
            connection.sendall(json.dumps(request).encode() + b"\n")
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if self.b.cli("status")["active"]:
                break
            time.sleep(0.025)
        else:
            admitted = self.members(self.a).get(self.b.identity) == "active"
            self.fail("lost-response join never installed state; issuer_admitted=%s" % admitted)
        before = self.state(self.a)
        self.join(self.b, path)
        self.b.stop()
        recovery = self.owned_sidecar(self.b.home / "network" / "transport")
        self.assertEqual(recovery.endpoint_id, self.b.identity)
        query = {"op": "join-status", "network_id": ticket["network_id"],
                 "invite_hash": hashlib.sha256(ticket["secret"].encode()).hexdigest()}
        confirmed = recovery.request(self.a.address, query, timeout=RPC_TIMEOUT)
        self.assertEqual(confirmed["origin"], self.a.identity)
        self.assertTrue(confirmed["body"]["ok"])
        self.assertEqual(confirmed["body"]["state"], before)
        missing = recovery.request(self.a.address, dict(query, invite_hash="0" * 64),
                                   timeout=RPC_TIMEOUT)
        self.assertEqual(missing["body"], {"ok": False, "code": "join-not-confirmed"})
        self.assertEqual(self.state(self.a), before, "join-status mutated admission history")
        recovery.close()
        self.b.start()
        self.join(self.b, path)
        self.assertEqual(self.state(self.a), before)
        c = self.node("c")
        result = self.join(c, path, success=False)
        self.assertEqual(result["code"], "join-refused-or-state-mismatch")
        self.assertNotIn(c.identity, self.members(self.a))
        self.assertFalse(c.cli("status")["active"])

    def test_failed_wrong_network_and_verified_wrong_state_preserve_active(self):
        requested = self.initialize(self.a, "requested")
        original = self.initialize(self.b, "retained")
        _, ticket = self.invite(self.a)
        active = self.b.home / "network" / "active.json"
        before = active.read_bytes()
        wrong = copy.deepcopy(ticket)
        wrong["network_id"] = "wrong-network-" + CANARY
        self.join(self.b, self.private_ticket("wrong-network", wrong), success=False)
        self.assertEqual(active.read_bytes(), before)
        # A live malicious endpoint wraps a genuinely signed B state in an A
        # network claim. The receiving service must check the verified root.
        probe = self.probe()
        retained_state = self.state(self.b)
        probe.set_request_handler(lambda origin, body: {
            "ok": True, "network_id": requested, "state": retained_state})
        substituted = dict(ticket, issuer=probe.address)
        error = self.join(self.b, self.private_ticket("substituted", substituted), success=False)
        self.assertEqual(active.read_bytes(), before)
        status = self.b.cli("status")
        self.assertTrue(status["active"])
        self.assertEqual(status["network"]["network_id"], original)
        self.assertEqual(self.state(self.b), retained_state)
        self.assertNotIn(self.b.identity, self.members(self.a))
        self.assertEqual(error["code"], "join-state-mismatch")

    def test_founder_offline_other_member_admits_c_and_c_leaves(self):
        network = self.initialize(self.a)
        path, _ = self.invite(self.a)
        self.join(self.b, path)
        self.a.stop()
        second_path, _ = self.invite(self.b)
        c = self.node("c")
        self.assertEqual(self.join(c, second_path)["network"]["network_id"], network)
        self.ping(self.b, c)
        self.ping(c, self.b)
        self.assertEqual(self.members(c), {node.identity: "active" for node in (self.a, self.b, c)})
        self.assertEqual(c.cli("leave")["status"], "left")
        self.assertFalse(c.cli("status")["active"])
        self.ping(c, self.b, success=False)
        # Departed devices cannot send business ping. Signed policy sync is
        # asynchronous and must carry the departure without granting work.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            rows = self.b.rpc({"op": "members"})["result"]["members"]
            if any(row["endpoint_id"] == c.identity and row["status"] == "removed" for row in rows):
                break
            time.sleep(0.05)
        else:
            self.fail("signed leave did not reach the remaining member via policy sync")
        self.assertEqual(self.members(self.b)[c.identity], "removed")

    def test_removed_caller_and_revoked_invitation_are_rejected(self):
        self.initialize(self.a)
        path, original_invite = self.invite(self.a)
        self.join(self.b, path)
        self.assertEqual(self.a.cli("remove", self.b.identity)["status"], "removed")
        self.assertEqual(self.ping(self.b, self.a, success=False)["code"], "peer-refused")
        self.assertEqual(self.members(self.a)[self.b.identity], "removed")
        original_hash = hashlib.sha256(original_invite["secret"].encode()).hexdigest()
        invites = self.a.cli("status")["network"]["invites"]
        original_rows = [row for row in invites if row["invite_hash"] == original_hash]
        self.assertEqual(len(original_rows), 1)
        self.assertTrue(original_rows[0]["revoked"], "remove did not revoke the old reusable link")
        old = self.join(self.b, path, success=False)
        self.assertEqual(old["code"], "join-refused-or-state-mismatch")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = self.b.rpc({"op": "status"})["result"]
            if not status["active"]:
                break
            time.sleep(0.05)
        else:
            self.fail("removed device did not learn its own signed removal")
        self.assertEqual(self.members(self.b)[self.b.identity], "removed")
        revoked_path, revoked = self.invite(self.a)
        invite_hash = hashlib.sha256(revoked["secret"].encode()).hexdigest()
        self.assertTrue(self.a.rpc({"op": "revoke-invite", "invite_hash": invite_hash})["ok"])
        self.join(self.b, revoked_path, success=False)
        self.assertEqual(self.members(self.a)[self.b.identity], "removed")

    def test_service_restart_retains_keys_membership_and_closes_listeners(self):
        network = self.initialize(self.a)
        path, _ = self.invite(self.a)
        self.join(self.b, path)
        identities = [self.a.identity, self.b.identity]
        for node in (self.a, self.b):
            key = node.home / "network" / "transport" / "node.secret"
            self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(key.parent.stat().st_mode), 0o700)
            node.stop()
            node.start()
            self.assertEqual(node.cli("status")["network"]["network_id"], network)
        self.assertEqual([self.a.identity, self.b.identity], identities)
        self.ping(self.a, self.b)
        self.ping(self.b, self.a)
        self.a.stop()
        self.b.stop()

    def test_native_wire_preserves_numbers_used_in_signed_membership(self):
        # Real timestamps have this magnitude and precision. Changing a single
        # bit changes canonical issued_at, the genesis hash and its signature.
        # These observed counterexamples make the native JSON regression
        # deterministic without patching the service clock or its signatures.
        values = [1793689766.9242175, 1793634999.9404047, 1793479100.4720573]
        self.initialize(self.a, "numbers")
        path, _ = self.invite(self.a)
        self.join(self.b, path)
        probe = self.probe()
        self.admit_probe(probe, self.a)
        self.ping(self.b, self.a)  # Merge the probe's actual signed admission.
        self.assertEqual(self.members(self.b)[probe.endpoint_id], "active")
        probe.set_request_handler(lambda origin, body: {"ok": True, "values": values})
        replies = [node.rpc({"op": "ping", "peer": probe.address})
                   for node in (self.a, self.b)]
        for reply in replies:
            self.assertTrue(reply["ok"])
            self.assertEqual(reply["result"]["values"], values,
                             "native JSON changed numbers used by signed issued_at")

    def test_real_crypto_wire_forgery_and_raw_error_nonreflection(self):
        network = self.initialize(self.a)
        path, _ = self.invite(self.a)
        self.join(self.b, path)
        probe = self.probe()
        self.admit_probe(probe, self.a)
        received = queue.Queue()
        def malicious(origin, body):
            received.put((origin, body))
            return {"ok": False, "code": CANARY, "detail": CANARY}
        probe.set_request_handler(malicious)
        error = self.a.rpc({"op": "ping", "peer": probe.address})
        self.assertEqual(error, {"ok": False, "code": "peer-refused"})
        origin, packet = received.get(timeout=2)
        self.assertEqual(origin, self.a.identity)
        self.assertEqual(packet["network_id"], network)
        wire = packet["state"]
        self.assertGreaterEqual(len(wire["records"]), 3)
        for record in wire["records"]:
            unsigned = {key: value for key, value in record.items() if key != "signature"}
            data = json.dumps(unsigned, sort_keys=True, ensure_ascii=True,
                              separators=(",", ":"), allow_nan=False).encode()
            self.assertTrue(probe.verify(record["issuer"], data, record["signature"]))
            self.assertFalse(probe.verify(record["issuer"], data + b"tamper", record["signature"]))
        before = self.state(self.a)
        forged = copy.deepcopy(wire)
        forged["records"][0]["machine_name"] = CANARY
        outsider = self.owned_sidecar(self.root / "wire-outsider")
        response = outsider.request(self.a.address, {
            "op": "sync", "network_id": network, "state": forged,
            "origin": self.b.identity, "secret": CANARY}, timeout=RPC_TIMEOUT)
        self.assertEqual(response["origin"], self.a.identity)
        self.assertEqual(response["body"], {"ok": False, "code": "invalid-or-unauthorized-request"})
        self.assert_no_secrets(json.dumps(response))
        self.assertEqual(self.state(self.a), before)
        refused = outsider.request(self.a.address, {
            "op": "sync", "network_id": network, "state": wire,
            "origin": self.b.identity}, timeout=RPC_TIMEOUT)
        self.assertEqual(refused["body"], {"ok": False, "code": "not-an-active-member"})
        # Stop B cleanly, then let the native engine reopen its own private key.
        # This gives the wire test an admitted TLS identity without reading keys
        # or substituting a membership/crypto fixture.
        self.b.stop()
        admitted = self.owned_sidecar(self.b.home / "network" / "transport")
        self.assertEqual(admitted.endpoint_id, self.b.identity)
        synchronized = admitted.request(self.a.address, {
            "op": "sync", "network_id": network, "state": wire,
            "address": admitted.address}, timeout=RPC_TIMEOUT)
        self.assertTrue(synchronized["body"]["ok"])
        self.assertEqual(synchronized["body"]["network_id"], network)
        self.assertEqual(synchronized["body"]["status"], "policy-updated")
        self.assertNotIn("state", synchronized["body"])
        self.assertNotIn("endpoint_id", synchronized["body"])
        denied = admitted.request(self.a.address, {
            "op": "sync", "network_id": network, "state": forged}, timeout=RPC_TIMEOUT)
        self.assertEqual(denied["body"], {"ok": False, "code": "invalid-or-unauthorized-request"})
        self.assertEqual(self.state(self.a), before)


if __name__ == "__main__":
    unittest.main()
