#!/usr/bin/env python3
"""Black-box stdio lifecycle and delivery checks; no xsm imports or storage inspection."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time


def require(condition, details):
    if not condition:
        raise AssertionError(details)


class Peer:
    def __init__(self, command, cwd, env, observations=None):
        self.observations = observations
        self.notifications = []
        self.frames = queue.Queue(maxsize=128)
        self.errors = tempfile.TemporaryFile()
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.errors)
        self.serial = 0
        def read():
            try:
                while True:
                    line = self.process.stdout.readline(4 * 1048576 + 1)
                    if not line:
                        raise RuntimeError("candidate closed stdout")
                    if len(line) > 4 * 1048576 or not line.endswith(b"\n"):
                        raise RuntimeError("candidate emitted an invalid or oversized frame")
                    self.frames.put(json.loads(line))
            except Exception as error:
                self.frames.put(error)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def call(self, method, params=None, error=None):
        self.serial += 1
        frame = {"jsonrpc": "2.0", "id": self.serial, "method": method, "params": params or {}}
        self.process.stdin.write((json.dumps(frame) + "\n").encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + 5
        while True:
            value = self.frames.get(timeout=max(0, deadline - time.monotonic()))
            if isinstance(value, Exception):
                raise value
            require(isinstance(value, dict) and value.get("jsonrpc") == "2.0", value)
            if "id" not in value:
                require(isinstance(value.get("method"), str) and isinstance(value.get("params"), dict), value)
                self.notifications.append(value)
                if self.observations is not None:
                    self.observations.append({"frame": value})
                continue
            require(type(value["id"]) is int and value["id"] == self.serial, value)
            require(("result" in value) != ("error" in value), value)
            if self.observations is not None:
                self.observations.append({"method": method, "frame": value})
            if error is not None:
                require(isinstance(value.get("error"), dict) and type(value["error"].get("code")) is int and value["error"]["code"] == error, value)
                return value["error"]
            require("result" in value, value)
            return value["result"]

    def notification(self):
        if self.notifications:
            return self.notifications.pop(0)
        value = self.frames.get(timeout=5)
        if isinstance(value, Exception):
            raise value
        require(isinstance(value, dict) and value.get("jsonrpc") == "2.0" and
                "id" not in value and isinstance(value.get("method"), str) and
                isinstance(value.get("params"), dict), value)
        if self.observations is not None:
            self.observations.append({"frame": value})
        return value

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        self.process.stdout.close()
        self.reader.join(timeout=1)
        self.errors.seek(0)
        diagnostics = self.errors.read(8192).decode(errors="replace")
        self.errors.close()
        return diagnostics


def messaging(peer, sender, receiver, reopen, check, equal, events=False):
    def operation(session, name, error=None, **arguments):
        return peer.call("operation.call", {"session": session["session"],
                         "operation": name, "arguments": arguments}, error=error)
    def report(claim, **fields):
        return peer.call("delivery.report", dict(session=receiver["session"], id=claim["id"], **fields))
    peer.call("events.subscribe", {"session": receiver["session"]})
    body = "black-box delivery: 한글 🚀 preserved\n  whitespace"
    operation(sender, "xsm_send", target="ref:" + receiver["ref"], text=body, wake="never", wait=0)
    packet = operation(receiver, "xsm_inbox", limit=1)
    check("stored original can be claimed whole", lambda: equal(len(packet["claims"]) == 1 and
          body in packet["messages"][0], True))
    claim = packet["claims"][0]
    check("foreign consumer cannot acknowledge", lambda:
          operation(sender, "xsm_ack", tokens=[claim["token"]], error=-32602))
    check("native admission requires exact claim", lambda: peer.call("delivery.report", {
          "session": receiver["session"], "id": claim["id"], "state": "admitted", "token": "forged"}, error=-32003))
    check("queued report is not consumption", lambda: equal(report(claim, state="queued")["acknowledged"], False))
    check("failed admission releases own claim", lambda: equal(peer.call("inbox.release", {
          "session": receiver["session"], "tokens": [claim["token"]]})["released"], [claim["id"]]))
    retry = operation(receiver, "xsm_inbox", limit=1)
    check("released original remains recoverable", lambda: equal(len(retry["claims"]) == 1 and
          retry["claims"][0]["id"] == claim["id"] and body in retry["messages"][0], True))
    current = retry["claims"][0]
    check("retry rotates claim token", lambda: equal(current["token"] != claim["token"], True))
    check("released claim cannot acknowledge", lambda:
          operation(receiver, "xsm_ack", tokens=[claim["token"]], error=-32602))
    check("admitted report is not consumption", lambda: equal(
          report(current, state="admitted", token=current["token"])["acknowledged"], False))
    peer.call("session.close", {"session": receiver["session"]})
    receiver = peer.call("session.open", reopen)
    check("resumed receiver rejects previous generation claim", lambda:
          operation(receiver, "xsm_ack", tokens=[current["token"]], error=-32602))
    resumed = operation(receiver, "xsm_inbox", limit=1)
    check("admitted original survives generation change", lambda: equal(len(resumed["claims"]) == 1 and
          resumed["claims"][0]["id"] == claim["id"] and body in resumed["messages"][0], True))
    token = resumed["claims"][0]["token"]
    check("explicit consumer ACK commits", lambda: equal(
          operation(receiver, "xsm_ack", tokens=[token])["acked"], [claim["id"]]))
    consumed = operation(receiver, "xsm_inbox")
    check("consumed original is absent from inbox", lambda: equal(
          consumed["claims"] == [] and consumed["messages"] == [], True))

    if events:
        peer.call("events.subscribe", {"session": receiver["session"]})
        operation(sender, "xsm_send", target="ref:" + receiver["ref"], text="event-bound original", wait=0)
        event = peer.notification()
        check("event binds receiver and pending IDs", lambda: equal(event["method"] == "events/available" and
              set(event["params"]) == {"session", "ids"} and event["params"]["session"] == receiver["session"] and
              len(event["params"]["ids"]) == 1, True))
        pending = operation(receiver, "xsm_inbox")
        check("notification neither claims nor consumes original", lambda: equal(len(pending["claims"]) == 1 and
              pending["claims"][0]["id"] == event["params"]["ids"][0] and
              "event-bound original" in pending["messages"][0], True))
        check("event original requires explicit ACK", lambda: equal(operation(receiver, "xsm_ack",
              tokens=[pending["claims"][0]["token"]])["acked"], event["params"]["ids"]))


def run(command, suite="lifecycle", capture=False):
    result = {"suite": "xsm-host-" + suite + "-v1", "status": "running", "checks": [],
              "scope": "stdio negotiation and participation only; no operations, delivery or UI certification"}
    peers = []
    observations = [] if capture else None
    if capture:
        result["observations"] = observations
    with tempfile.TemporaryDirectory(prefix="xsm-conformance-") as folder:
        env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR", "SYSTEMROOT") if key in os.environ}
        env.update(HOME=folder, XSM_HOME=folder + "/state", CODEX_HOME=folder + "/codex",
                   CLAUDE_CONFIG_DIR=folder + "/claude", PYTHONDONTWRITEBYTECODE="1")
        def check(name, action):
            result["activeCheck"] = name
            action()
            result["checks"].append(name)
        def equal(actual, expected):
            require(actual == expected, {"actual": actual, "expected": expected})
        try:
            a = Peer(command, folder, env, observations)
            peers.append(a)
            check("initialize required", lambda: a.call("operations/list", error=-32002))
            check("unsupported version refused", lambda: a.call("initialize", {"protocolVersion": "unsupported"}, error=-32002))
            check("version negotiated", lambda: equal(a.call("initialize", {"protocolVersion": "1"})["protocolVersion"], "1"))
            check("duplicate initialize refused", lambda: a.call("initialize", {"protocolVersion": "1"}, error=-32600))
            operations = a.call("operations/list")["operations"]
            check("operation descriptors", lambda: equal(all(isinstance(o.get("name"), str) and
                  isinstance(o.get("inputSchema"), dict) for o in operations) and bool(operations), True))
            params = dict(runtime="conformance", profile="isolated", conversation="a", cwd=folder,
                          capabilities=["messaging", "inbox"])
            check("native impersonation refused", lambda: a.call("session.open", dict(params, runtime="codex"), error=-32602))
            first = a.call("session.open", params)
            check("opaque participation fields", lambda: equal(all(isinstance(first.get(k), str) and
                  first[k] and folder not in first[k] for k in ("session", "generation", "ref")), True))
            check("immutable session identity", lambda: a.call("session.update", {"session": first["session"], "cwd": folder}, error=-32602))
            check("state update", lambda: equal(a.call("session.update", {"session": first["session"], "state": "busy"})["state"], "busy"))
            b = Peer(command, folder, env, observations)
            peers.append(b)
            b.call("initialize", {"protocolVersion": "1"})
            check("connection-local handles", lambda: b.call("session.update", {"session": first["session"], "state": "idle"}, error=-32001))
            check("single live conversation owner", lambda: b.call("session.open", params, error=-32003))
            other = a.call("session.open", dict(params, profile="other"))
            check("profile isolation", lambda: equal(other["ref"] != first["ref"], True))
            check("explicit close", lambda: equal(a.call("session.close", {"session": first["session"]}), {"closed": True}))
            check("closed handle refused", lambda: a.call("session.update", {"session": first["session"], "state": "idle"}, error=-32001))
            reopened = b.call("session.open", params)
            check("stable address new generation", lambda: equal(reopened["ref"] == first["ref"] and
                  reopened["generation"] != first["generation"] and reopened["session"] != first["session"], True))
            a.close()
            peers.remove(a)
            resumed = b.call("session.open", dict(params, profile="other"))
            check("EOF releases conversation ownership", lambda: equal(resumed["ref"] == other["ref"] and
                  resumed["generation"] != other["generation"], True))
            if suite in ("messaging", "events"):
                result["scope"] = "lifecycle and claim/queue/ACK recovery; no native delivery, UI or complete operations certification"
                messaging(b, reopened, resumed, dict(params, profile="other"), check, equal, events=suite == "events")
            result.update(status="passed", activeCheck=None)
        except Exception as error:
            result.update(status="failed", error=repr(error))
        finally:
            result["diagnostics"] = [peer.close() for peer in peers]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true", help="include isolated wire observations in the report")
    parser.add_argument("--suite", choices=("lifecycle", "messaging", "events"), default="lifecycle")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    if not args.command:
        parser.error("--command requires an executable")
    result = run(args.command, args.suite, args.capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), "activeCheck": result["activeCheck"]}))
    raise SystemExit(0 if result["status"] == "passed" else 1)
