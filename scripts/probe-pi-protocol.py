#!/usr/bin/env python3
"""Pi RPC admission/UI probe, with no configured model or credentials.

This verifies native RPC and queue paths, not model replies or physical UI.
Every process gets a fresh HOME and a temporary repository. Evidence is kept.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "clients/python"))
from xsm_client import XsmClient


class NativePi:
    def __init__(self, process, output):
        self.process = process
        self.lines = []
        self.events = []
        self.stdout_file = (output / "native.stdout").open("w")
        self.stderr_file = (output / "native.stderr").open("w")
        self.stderr = asyncio.create_task(self.drain_stderr())

    async def drain_stderr(self):
        while True:
            data = await self.process.stderr.read(65536)
            if not data:
                break
            self.stderr_file.write(data.decode())
            self.stderr_file.flush()

    async def send(self, value):
        self.process.stdin.write((json.dumps(value) + "\n").encode())
        await self.process.stdin.drain()

    async def until(self, predicate, timeout=15):
        async def receive():
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    raise RuntimeError("Pi closed stdout before expected native event")
                self.lines.append(line.decode())
                self.stdout_file.write(line.decode())
                self.stdout_file.flush()
                event = json.loads(line)
                self.events.append(event)
                if predicate(event):
                    return event
        return await asyncio.wait_for(receive(), timeout)

    async def command(self, ident, message):
        result = await self.rpc(ident, "prompt", message=message)
        assert result.get("success") and result.get("data", {}).get("disposition") == "handled", result
        return result

    async def rpc(self, ident, kind, **params):
        await self.send({"type": kind, "id": ident, **params})
        result = await self.until(lambda event: event.get("id") == ident and event.get("type") == "response")
        assert result.get("success"), result
        return result


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="xsm-pi-probe-"))
    project, home, pi_home, state = [temp / name for name in ("project", "home", "pi", "state")]
    for path in (project, home, pi_home):
        path.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    # An unknown-model fixture must not enter automatic retry/compaction loops.
    (pi_home / "settings.json").write_text(json.dumps({"compaction": {"enabled": False}, "retry": {"enabled": False}}))
    env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR") if key in os.environ}
    env.update(HOME=str(home), PI_CODING_AGENT_DIR=str(pi_home), XSM_HOME=str(state),
               XSM_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE="1")
    version = subprocess.run(["node", str(args.pi_cli), "--version"], cwd=project,
                             env=env, capture_output=True, text=True, check=True).stdout.strip()
    if version != "1.4.0":
        raise RuntimeError("probe requires the pinned Pi 1.4.0; observed " + version)
    installation = None
    extension_args = ["-e", str(ROOT / "integrations/pi/xsm.mjs")]
    if args.installed:
        command = [str(ROOT / "bin/xsm"), "protocol", "install", "pi", "--home", str(pi_home)]
        installed = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, check=True)
        installation = json.loads(installed.stdout)
        extension_args = []  # Native discovery must load the installed profile, not -e.
        env.pop("XSM_PYTHON", None)
        env.pop("PYTHONPATH", None)
    process = await asyncio.create_subprocess_exec("node", str(args.pi_cli), "--mode", "rpc", "--no-session",
        *extension_args, cwd=str(project), env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, start_new_session=True)
    native = NativePi(process, args.output)
    sender = None
    result = {"status": "running", "root": str(temp), "nativePid": process.pid, "samplesRequested": args.samples,
              "installation": installation,
              "runtimeVersion": version, "platform": sys.platform, "python": sys.version.split()[0],
              "sourceSha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                  for name in ("integrations/pi/xsm.mjs", "clients/typescript/xsm-host.mjs",
                               "xsm/protocol.py", "xsm/receive.py", "scripts/probe-pi-protocol.py")},
              "modelConfigured": False, "physicalHumanUiTested": False, "samples": [],
              "measurement": "send initiation to native message_start observation; upper bound on store-to-admission"}
    def checkpoint():
        pending = args.output / "result.tmp"
        pending.write_text(json.dumps(result, indent=2) + "\n")
        pending.replace(args.output / "result.json")
    checkpoint()
    try:
        await native.send({"type": "get_state", "id": "initial"})
        initial = (await native.until(lambda e: e.get("id") == "initial"))["data"]
        assert initial["model"]["provider"] == "unknown" and initial["model"]["baseUrl"] == "", initial
        result["initial"] = initial
        await native.command("status", "/xsm status")
        statuses = [json.loads(e["message"]) for e in native.events
                    if e.get("type") == "extension_ui_request" and e.get("method") == "notify"]
        own = next(s for s in statuses if "ref" in s)
        assert set(own["operations"]) == set(own["nativeTools"]), own
        result["nativeToolCount"] = len(own["nativeTools"])
        if installation:
            native_records = [json.loads(p.read_text()) for p in (state / "sessions").glob("*.json")]
            actual = next(item for item in native_records if item["runtime"] == "pi")
            assert actual["protocol_root"] == os.path.realpath(installation["runtime_root"]), actual
            assert actual["protocol_python_version"] == sys.version.split()[0], actual
            result["snapshotRuntimeVerified"] = True
        if getattr(args, "crash", False):
            native_records = [json.loads(p.read_text()) for p in (state / "sessions").glob("*.json")]
            previous = next(item for item in native_records if item["runtime"] == "pi")
            assert previous["pid"] != process.pid and os.getpgid(previous["pid"]) == process.pid, "backend is not in the probe process group"
            os.kill(previous["pid"], signal.SIGKILL)
            deadline = time.monotonic() + 5
            while True:
                try:
                    os.kill(previous["pid"], 0)
                except ProcessLookupError:
                    break
                assert time.monotonic() < deadline, "backend was not reaped"
                await asyncio.sleep(.01)
            await native.command("recovered-status", "/xsm status")
            current_records = [json.loads(p.read_text()) for p in (state / "sessions").glob("*.json")]
            recovered = next(item for item in current_records if item["runtime"] == "pi")
            assert recovered["ref"] == previous["ref"] and recovered["pid"] != previous["pid"]
            assert recovered["protocol_generation"] != previous["protocol_generation"]
            result["backendRecovery"] = {"sameRef": True, "generationChanged": True,
                "oldPid": previous["pid"], "newPid": recovered["pid"], "trigger": "native /xsm status; no failed operation replay"}
            checkpoint()
        # Exercise the real native select dialog protocol. The driver supplies
        # the answer; this is not attributed to a physical human.
        await native.send({"type": "prompt", "id": "question", "message": "/xsm xsm_decide " +
            json.dumps({"question": "XSM Pi RPC probe: choose a color", "options": ["blue", "green"]})})
        form = await native.until(lambda e: e.get("type") == "extension_ui_request" and e.get("method") == "select")
        assert form["title"] == "XSM Pi RPC probe: choose a color" and form["options"] == ["blue", "green"]
        await native.send({"type": "extension_ui_response", "id": form["id"], "value": "blue"})
        question = await native.until(lambda e: e.get("id") == "question")
        assert question.get("success"), question
        records = [json.loads(p.read_text()) for p in (state / "human-decisions").glob("*.json")]
        assert len(records) == 1 and records[0]["status"] == "applied", records
        assert records[0]["answer"]["source"] == "host-user"
        result["nativeRpcUi"] = {"status": "passed", "answer": "blue", "source": "host-user"}

        sender = await XsmClient.connect([str(ROOT / "bin/xsm"), "protocol", "serve", "--stdio"],
                                         cwd=str(project), env=env)
        origin = await sender.session_open(runtime="native-probe", profile="sender", conversation="sender",
                                           cwd=str(project), capabilities=[])
        for index in range(args.samples):
            marker = "native-admission-%d" % index
            started = time.perf_counter()
            await sender.operation_call(origin["session"], "xsm_send", {
                "target": "ref:" + own["ref"], "text": marker, "wait": 0})
            event = await native.until(lambda e: e.get("type") == "message_start" and
                e.get("message", {}).get("customType") == "xsm" and marker in str(e["message"].get("content")))
            elapsed = time.perf_counter() - started
            ids = event["message"]["details"]["messages"]
            assert len(ids) == 1
            path = next((state / "handoffs").glob("*/" + ids[0] + ".json"))
            original = json.loads(path.read_text())
            assert original["state"] != "acknowledged"
            await native.until(lambda e: e.get("type") == "agent_settled")
            await native.command("ack-%d" % index,
                "/xsm xsm_ack " + json.dumps({"tokens": [original["claim"]["token"]]}))
            assert json.loads(path.read_text())["state"] == "acknowledged"
            result["samples"].append({"index": index, "id": ids[0], "upperBoundSeconds": elapsed})
            checkpoint()
            print(json.dumps(result["samples"][-1]), flush=True)
        values = sorted(s["upperBoundSeconds"] for s in result["samples"])
        if values:
            import math
            result["p95UpperBoundSeconds"] = values[math.ceil(len(values) * .95) - 1]
            result["latencyGate"] = "pilot" if args.samples < 100 else "passed"
            if args.samples >= 100 and result["p95UpperBoundSeconds"] > 1:
                result["latencyGate"] = "failed"
                raise AssertionError("native admission p95 upper bound exceeds one second")
        result["status"] = "passed"
    except Exception as error:
        result["status"] = "failed"
        result["error"] = repr(error)
    except asyncio.CancelledError:
        result.update(status="interrupted", error="probe deadline or caller cancellation")
        raise
    finally:
        if sender:
            await sender.close()
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 8)
        except asyncio.TimeoutError:
            os.killpg(process.pid, signal.SIGTERM)
            await process.wait()
            result["forcedTermination"] = True
        result["exit"] = process.returncode
        if process.returncode or result.get("forcedTermination"):
            result["status"] = "failed"
        await native.stderr
        native.stdout_file.close()
        native.stderr_file.close()
        checkpoint()
        print(json.dumps({k: v for k, v in result.items() if k not in ("initial", "samples")}), flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--crash", action="store_true")
    parser.add_argument("--installed", action="store_true", help="test profile autoload from an owned runtime snapshot")
    options = parser.parse_args()
    if options.samples < 0:
        parser.error("samples must be nonnegative")
    async def bounded_run():
        return await asyncio.wait_for(run(options), 150)
    raise SystemExit(asyncio.run(bounded_run()))
