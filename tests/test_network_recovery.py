"""Regressions for the two frozen Opus findings, not another model review.

The recovery case runs a real private CLI/Python service and Rust engine. Only
its verified direct child engine receives a signal. Peer-transition cases use
server-level RPC fixtures combined with actual Rust sign/verify callbacks; they
do not claim QUIC or physical-machine transition coverage. The liveness cases
reuse the existing fake JSONL engine and are not cryptographic evidence.
"""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests import test_network_service as service_tests
from tests import test_network_transport as transport_tests
from xsm import network, network_transport as transport, paths
from xsm.network_membership import MembershipStore


def evidence(event, **fields):
    """Optional evaluator log contains public IDs/counts/digests, never keys/tickets."""
    destination = os.environ.get("XSM_RECOVERY_EVIDENCE")
    if destination:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(dict(event=event, python=sys.version.split()[0], **fields)) + "\n")


class _CurrentModulesCase(unittest.TestCase):
    def setUp(self):
        global network, transport, paths, MembershipStore
        from xsm import network, network_transport as transport, paths
        from xsm.network_membership import MembershipStore


class ActualServiceRecoveryTests(_CurrentModulesCase):
    def setUp(self):
        super().setUp()
        self.binary = transport.find_binary()  # A missing binary fails; no build/skip.
        self.temporary = tempfile.TemporaryDirectory(prefix="xrec-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.temp_dir = self.root / "tmp"
        self.temp_dir.mkdir(mode=0o700)
        self.outputs = []
        self.secrets = [service_tests.CANARY]

    def assert_no_secrets(self, text):
        for value in self.secrets:
            self.assertNotIn(value, text)

    def wait_for(self, condition, label, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.025)
        self.fail(label)

    def test_owned_engine_exit_releases_listener_lock_and_cli_start_preserves_identity(self):
        node = service_tests.ServiceNode(self, "owned")
        self.addCleanup(node.cleanup)
        node.start()
        initialized = node.cli("init", "recovery-network", "--machine-name", "owned")
        invitation = node.cli("invite", "--once", "--expires", "60")
        self.assertTrue(Path(invitation["ticket_file"]).is_file())
        before = node.cli("status")
        old_service, old_engine = before["service_pid"], before["engine_pid"]
        self.assertEqual(old_service, node.process.pid)
        self.assertEqual(old_engine, node.sidecar_pid)
        table = service_tests.process_table()
        self.assertEqual(table[old_engine][0], node.process.pid)
        self.assertEqual(Path(table[old_engine][1]).name, "xsm-net")
        owner = subprocess.run(["ps", "-p", str(old_engine), "-o", "uid="],
                               capture_output=True, text=True, check=True, timeout=3)
        self.assertEqual(int(owner.stdout.strip()), os.geteuid())
        directory = node.home / "network"
        roster = directory / "networks" / hashlib.sha256(initialized["network"]["network_id"].encode()).hexdigest() / "membership.json"
        original_roster = roster.read_bytes()
        original_active = (directory / "active.json").read_bytes()
        original_tickets = {p.name: p.read_bytes() for p in (directory / "invites").iterdir()}
        with (directory / "service.lock").open("rb") as lock:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Deliberately kill only the PID returned by our private service, after
        # checking the live Popen parent, executable name and effective UID.
        os.kill(old_engine, signal.SIGKILL)
        evidence("owned_engine_signalled", service_pid=old_service, engine_pid=old_engine,
                 verified_uid=os.geteuid(), verified_parent=node.process.pid, signal="SIGKILL")
        self.wait_for(lambda: node.process.poll() is not None,
                      "engine EOF did not stop its owning Python daemon")
        self.assertEqual(node.process.returncode, 0)
        self.assertFalse(node.socket.exists(), "dead-engine daemon kept the Unix listener")
        with socket.socket(socket.AF_UNIX) as client:
            with self.assertRaises(OSError):
                client.connect(str(node.socket))
        with (directory / "service.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for address in before["transport"]["bound_addresses"]:
            if not address.startswith("["):
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
                    listener.bind(("0.0.0.0", int(address.rsplit(":", 1)[1])))
        recovered = {}

        def stop_recovered():
            # The replacement is daemonized by the public CLI, not our Popen.
            # Stop only through this test's private socket; never signal its PID.
            if node.socket.exists():
                node.cli("stop")
                self.wait_for(lambda: not node.socket.exists(), "recovered listener survived stop")
            if recovered:
                self.wait_for(lambda: recovered["engine_pid"] not in service_tests.process_table(),
                              "recovered native engine survived private stop")

        self.addCleanup(stop_recovered)
        with mock.patch.object(node, "cli", wraps=node.cli) as calls:
            recovered.update(node.cli("start"))
            self.assertEqual([c.args[0] for c in calls.call_args_list], ["start"])
        self.assertNotEqual(recovered["service_pid"], old_service)
        self.assertNotEqual(recovered["engine_pid"], old_engine)
        self.assertEqual(recovered["endpoint_id"], before["endpoint_id"])
        self.assertEqual(recovered["network"], before["network"])
        self.assertTrue(recovered["active"])
        self.assertEqual(roster.read_bytes(), original_roster)
        self.assertEqual((directory / "active.json").read_bytes(), original_active)
        self.assertEqual({p.name: p.read_bytes() for p in (directory / "invites").iterdir()}, original_tickets)
        self.assertEqual(len(original_tickets), 1)
        self.assertEqual(stat.S_IMODE(node.socket.stat().st_mode), 0o600)
        evidence("actual_cli_recovery", old_service_pid=old_service, old_engine_pid=old_engine,
                 new_service_pid=recovered["service_pid"], new_engine_pid=recovered["engine_pid"],
                 endpoint_id=recovered["endpoint_id"], network_id=recovered["network"]["network_id"],
                 listener_released=True, service_lock_released=True, udp_port_released=True,
                 roster_sha256=hashlib.sha256(original_roster).hexdigest(),
                 business_operations_replayed=0, ticket_count_before=1, ticket_count_after=1)


class PrivateDirectoryTests(_CurrentModulesCase):
    def test_missing_ancestors_are_private_and_existing_nonprivate_modes_are_preserved(self):
        # Reproduce a usual clean build under 0022 deterministically. This is
        # process-local and restored even when the assertion/old helper fails.
        previous_umask = os.umask(0o022)
        try:
            with tempfile.TemporaryDirectory(prefix="xrec-parents-") as root:
                root = Path(root)
                state = root / "not-created-yet"
                destination = state / "network" / "bin"
                network._private_directory(destination)
                for directory in (state, state / "network", destination):
                    self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700,
                                     "new ancestor was not private: " + directory.name)
                # configure validates network itself after build created bin.
                network._private_directory(state / "network")
                existing = root / "existing-nonprivate"
                existing.mkdir(mode=0o755)
                with self.assertRaisesRegex(network.NetworkError, "non-private-state-directory"):
                    network._private_directory(existing)
                self.assertEqual(stat.S_IMODE(existing.stat().st_mode), 0o755)
                child = existing / "new-network" / "bin"
                network._private_directory(child)
                self.assertEqual(stat.S_IMODE(existing.stat().st_mode), 0o755)
                for directory in (child.parent, child):
                    self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        finally:
            os.umask(previous_umask)


class StartRaceTests(_CurrentModulesCase):
    def test_start_retries_only_service_after_zero_exit_and_listener_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            location = mock.Mock()
            location.exists.side_effect = [True, False]
            lost_race = mock.Mock(returncode=0)
            lost_race.poll.return_value = 0
            replacement = mock.Mock(returncode=None)
            replacement.poll.return_value = None
            running = {"status": "running", "engine_pid": 12345}
            with mock.patch.object(paths, "HOME", root), \
                    mock.patch.object(network, "socket_path", return_value=location), \
                    mock.patch.object(network, "call", side_effect=[network.NetworkError("request-failed")] * 3 + [running]) as rpc, \
                    mock.patch.object(network.subprocess, "Popen", side_effect=[lost_race, replacement]) as spawn, \
                    mock.patch.object(network.time, "sleep"):
                self.assertEqual(network.start(timeout=1), running)
            self.assertEqual(spawn.call_count, 2)
            self.assertEqual(location.exists.call_count, 2)
            for call in spawn.call_args_list:
                self.assertEqual(call.args[0], [sys.executable, "-B", "-m", "xsm.network", "serve"])
            self.assertTrue(all(c.args[0] == {"op": "status"} for c in rpc.call_args_list))
            evidence("start_zero_exit_race", fixture=True, service_spawns=2, status_calls=rpc.call_count,
                     business_operations_replayed=0)

    def test_nonzero_service_exit_is_not_retried(self):
        with tempfile.TemporaryDirectory() as root:
            failed = mock.Mock(returncode=17)
            failed.poll.return_value = 17
            with mock.patch.object(paths, "HOME", root), \
                    mock.patch.object(network, "call", side_effect=network.NetworkError("request-failed")), \
                    mock.patch.object(network.subprocess, "Popen", return_value=failed) as spawn:
                with self.assertRaisesRegex(network.NetworkError, "service-start-failed"):
                    network.start(timeout=1)
            spawn.assert_called_once()


class PeerTransitionTests(_CurrentModulesCase):
    """Real Rust cryptography; server/RPC fixtures, not an actual QUIC switch."""

    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory(prefix="xrec-peer-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        binary = transport.find_binary()
        self.local_node, self.old_node, self.new_node = [
            transport.Sidecar(self.root / ("native-" + name), relay="off", binary=binary)
            for name in ("local", "old", "new")]
        for node in (self.local_node, self.old_node, self.new_node):
            self.addCleanup(node.close)
            node.start(timeout=5)
        patched = mock.patch.object(network, "root", return_value=self.root / "daemon")
        patched.start()
        self.addCleanup(patched.stop)
        self.wire = mock.Mock(wraps=self.local_node)
        self.wire.endpoint_id = self.local_node.endpoint_id
        self.wire.address = self.local_node.address
        self.wire.process_id = self.local_node.process_id
        self.wire.last_transport = None
        self.daemon = network.Daemon(self.wire)
        self.daemon.ready = {"fixture": "RPC only; signatures verified by Rust"}
        old_state, _ = self.admission(self.old_node, "old")
        self.new_state, self.ticket = self.admission(self.new_node, "new")
        self.daemon._install(old_state)
        self.daemon._peers[self.old_node.endpoint_id] = self.old_node.address
        self.daemon._save_peers()

        def respond(peer, body, timeout):
            if body["op"] == "join":
                self.assertEqual(peer, self.new_node.address)
                return {"origin": self.new_node.endpoint_id,
                        "body": {"ok": True, "network_id": self.new_state["network_id"],
                                 "state": copy.deepcopy(self.new_state)}}
            return {"origin": peer["id"], "body": {"ok": True}}

        self.wire.request.side_effect = respond

    def admission(self, issuer, name):
        store = MembershipStore(self.root / ("membership-" + name), issuer.endpoint_id,
                                issuer.sign, issuer.verify)
        store.initialize(name, name)
        invite = store.issue_invite(lifetime_seconds=60)
        state = store.redeem(invite["secret"], self.local_node.endpoint_id, "local")["state"]
        return state, {"version": 1, "network_id": state["network_id"],
                       "issuer": issuer.address, "secret": invite["secret"], "reusable": True}

    def switch(self):
        status = self.daemon._join(self.ticket, "local")
        self.assertEqual(status["network"]["network_id"], self.new_state["network_id"])
        self.wire.request.reset_mock()

    def sync_once(self):
        with mock.patch.object(self.daemon._stop, "wait", side_effect=[False, True]):
            self.daemon.synchronize()

    def test_switch_loads_only_destination_peers_and_syncs_current_membership(self):
        # A saved destination cache may contain an address from another group.
        cache = network.root() / ("peers-" + hashlib.sha256(self.new_state["network_id"].encode()).hexdigest() + ".json")
        paths.write_json(str(cache), {self.old_node.endpoint_id: self.old_node.address,
                                     self.new_node.endpoint_id: self.new_node.address})
        self.switch()
        self.assertEqual(self.daemon._peers, {self.new_node.endpoint_id: self.new_node.address})
        self.assertEqual(json.loads(cache.read_text()), self.daemon._peers)
        self.sync_once()
        self.wire.request.assert_called_once()
        call = self.wire.request.call_args
        self.assertEqual(call.args[0], self.new_node.address)
        self.assertEqual(call.args[1]["state"]["network_id"], self.new_state["network_id"])
        evidence("peer_switch", server_rpc_fixture=True, actual_rust_sign_verify=True,
                 old_peer_retained=False, sync_recipient=self.new_node.endpoint_id,
                 old_peer_sync_requests=0, new_network_id=self.new_state["network_id"])

    def test_stale_previous_peer_sync_is_rejected_before_transport(self):
        self.switch()
        with self.assertRaisesRegex(network.NetworkError, "peer-refused"):
            self.daemon.rpc(self.old_node.address, {"op": "sync"})
        self.wire.request.assert_not_called()
        # Even if a stale address is reintroduced, the sending guard must stop it.
        self.daemon._peers[self.old_node.endpoint_id] = self.old_node.address
        self.sync_once()
        self.assertEqual([c.args[0] for c in self.wire.request.call_args_list], [self.new_node.address])
        evidence("stale_peer_sync", server_rpc_fixture=True, actual_rust_sign_verify=True,
                 old_peer_sync_requests=0, direct_sync_refused=True)


class SidecarLivenessTests(_CurrentModulesCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory(prefix="xrec-fake-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.binary = self.root / "fake-engine"
        self.binary.write_text("#!%s\n%s" % (sys.executable, transport_tests.FAKE_ENGINE))
        self.binary.chmod(0o700)
        self.sidecar = transport.Sidecar(self.root / "normal", binary=self.binary)
        self.addCleanup(self.sidecar.close)

    def test_running_and_process_id_track_fake_engine_eof_and_close(self):
        self.assertFalse(self.sidecar.running)
        self.assertIsNone(self.sidecar.process_id)
        self.sidecar.start(timeout=3)
        pid = self.sidecar.process_id
        self.assertEqual(pid, self.sidecar._process.pid)
        self.assertTrue(self.sidecar.running)
        cached_identity = self.sidecar.endpoint_id
        with self.assertRaisesRegex(transport.SidecarError, "process_exited"):
            self.sidecar.request({}, {"action": "stdout-eof"}, timeout=2)
        self.assertTrue(self.sidecar._cleanup_done.wait(3))
        self.assertEqual(self.sidecar.endpoint_id, cached_identity)
        self.assertFalse(self.sidecar.running)
        self.sidecar.close()
        self.assertFalse(self.sidecar.running)
        self.assertEqual(self.sidecar.process_id, pid)

    def test_running_checks_process_poll_before_watch_thread_reports_failure(self):
        self.sidecar.start(timeout=3)
        with mock.patch.object(self.sidecar._process, "poll", return_value=0):
            self.assertIsNone(self.sidecar._failure)
            self.assertFalse(self.sidecar.running)


if __name__ == "__main__":
    unittest.main()
