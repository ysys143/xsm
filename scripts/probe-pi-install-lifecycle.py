#!/usr/bin/env python3
"""Existing-session install/upgrade/resume/uninstall using owned Pi RPC processes."""
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pi_probe_driver", ROOT / "scripts/probe-pi-protocol.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="xsm-pi-lifecycle-"))
    project, home, pi_home, state = [temp / name for name in ("project", "home", "pi", "state")]
    for path in (project, home, pi_home):
        path.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    settings = pi_home / "settings.json"
    settings.write_text('{"compaction":{"enabled":false},"retry":{"enabled":false},"sentinel":"keep"}')
    before_settings = settings.read_bytes()
    env = {k: os.environ[k] for k in ("PATH", "LANG", "TMPDIR") if k in os.environ}
    env.update(HOME=str(home), PI_CODING_AGENT_DIR=str(pi_home), XSM_HOME=str(state),
               XSM_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE="1")
    # Pi deliberately does not persist sessions without an assistant message.
    # Seed one through its public SessionManager, explicitly as fixture data.
    seed_source = '''const sdk = await import(process.argv[1]);
const manager = sdk.SessionManager.create(process.argv[2], process.argv[3]);
manager.appendMessage({role:'assistant', content:[{type:'text',text:'retained-session-context'}],
 api:'unknown',provider:'unknown',model:'offline-fixture',stopReason:'stop',timestamp:Date.now(),
 usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,
 cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}});
console.log(JSON.stringify({file:manager.getSessionFile(),id:manager.getSessionId()}));'''
    sdk_uri = (args.pi_cli.resolve().parents[2] / "dist/index.js").as_uri()
    seed = subprocess.run(["node", "--input-type=module", "-e", seed_source, sdk_uri,
                           str(project), str(pi_home / "sessions")], env=env, capture_output=True, text=True, check=True)
    seeded = json.loads(seed.stdout)
    native = None
    phase = 0
    result = {"status": "incomplete", "root": str(temp), "modelCalls": False, "assistantFixture": True, "phases": []}

    async def start(session=None):
        nonlocal phase
        output = args.output / ("phase-%d" % phase)
        output.mkdir()
        phase += 1
        process_env = dict(env)
        process_env.pop("XSM_PYTHON", None)
        command = ["node", str(args.pi_cli), "--mode", "rpc"]
        if session:
            command += ["--session", str(session)]
        process = await asyncio.create_subprocess_exec(*command, cwd=project, env=process_env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True)
        return driver.NativePi(process, output)

    async def stop(item):
        item.process.stdin.close()
        try:
            await asyncio.wait_for(item.process.wait(), 8)
        except asyncio.TimeoutError:
            os.killpg(item.process.pid, signal.SIGTERM)
            await item.process.wait()
            raise AssertionError("owned native process required forced termination")
        await item.stderr
        item.stdout_file.close()
        item.stderr_file.close()
        assert item.process.returncode == 0

    def install_from(source, action):
        done = subprocess.run([str(source / "bin/xsm"), "protocol", action, "pi", "--home", str(pi_home)],
            cwd=project, env=env, capture_output=True, text=True, check=True)
        return json.loads(done.stdout)

    def protocol_record():
        records = [json.loads(p.read_text()) for p in (state / "sessions").glob("*.json")]
        return next(item for item in records if item["runtime"] == "pi")

    def prune_owned_snapshots():
        # Observe only this test's registered processes, not other user argv.
        # The snapshot-id parser has a separate bare-launcher-root regression.
        source = '''import json, os, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from xsm import install, registry, identity
install._running_from = lambda: {Path(r['protocol_root']).name for r in registry.raw_records()
 if r.get('protocol_root') and identity.pid_alive(r.get('pid'))}
install._live_session_starts = lambda: []
print(json.dumps(install.prune_snapshots()))'''
        done = subprocess.run([sys.executable, "-c", source, str(ROOT)], cwd=project,
                              env=env, capture_output=True, text=True, check=True)
        return json.loads(done.stdout)

    try:
        native = await start(Path(seeded["file"]))
        initial = (await native.rpc("initial", "get_state"))["data"]
        assert initial["model"]["provider"] == "unknown"
        commands = (await native.rpc("commands-before", "get_commands"))["data"]["commands"]
        assert not any(command["name"] == "xsm" for command in commands)
        await native.rpc("persist", "bash", command="printf retained-session-context")
        original_id = initial["sessionId"]
        files = list((pi_home / "sessions").rglob("*.jsonl"))
        session_file = next(path for path in files if json.loads(path.read_text().splitlines()[0])["id"] == original_id)
        first = install_from(ROOT, "install")
        commands = (await native.rpc("commands-after-install", "get_commands"))["data"]["commands"]
        assert not any(command["name"] == "xsm" for command in commands), "install must not pretend to hot-reload"
        result["phases"].append("install reports reload required for an existing session")
        await stop(native)
        native = await start(session_file)
        resumed = (await native.rpc("resumed", "get_state"))["data"]
        assert resumed["sessionId"] == original_id
        messages = (await native.rpc("retained", "get_messages"))["data"]["messages"]
        assert "retained-session-context" in json.dumps(messages)
        await native.command("status-loaded", "/xsm status")
        old = protocol_record()
        assert old["protocol_root"] == os.path.realpath(first["runtime_root"])
        assert old["protocol_python_version"] == sys.version.split()[0]
        result["phases"].append("same native session and context resume with the installed loader")

        clone = temp / "upgrade-source"
        for part in ("xsm", "hooks", "skills", "bin", "clients", "integrations", ".claude-plugin", ".codex-plugin"):
            shutil.copytree(ROOT / part, clone / part, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "LICENSE", clone / "LICENSE")
        with (clone / "xsm/paths.py").open("a") as stream:
            stream.write("\n# isolated upgrade revision\n")
        second = install_from(clone, "install")
        assert second["runtime_root"] != first["runtime_root"]
        await native.command("old-still-loaded", "/xsm status")
        assert protocol_record()["protocol_root"] == old["protocol_root"]
        assert Path(first["runtime_root"]).is_dir()
        assert Path(first["runtime_root"]).name not in prune_owned_snapshots()
        result["phases"].append("upgrading the loader preserves the running old snapshot")
        await stop(native)
        native = await start(session_file)
        assert (await native.rpc("updated", "get_state"))["data"]["sessionId"] == original_id
        await native.command("new-loaded", "/xsm status")
        updated = protocol_record()
        assert updated["protocol_root"] == os.path.realpath(second["runtime_root"])
        assert updated["ref"] == old["ref"] and updated["protocol_generation"] != old["protocol_generation"]
        assert Path(first["runtime_root"]).name in prune_owned_snapshots()
        result["phases"].append("resume loads new snapshot with stable identity and fresh generation")
        removed = install_from(ROOT, "uninstall")
        assert removed["status"] == "removed"
        await native.command("still-running", "/xsm status")
        assert settings.read_bytes() == before_settings
        result["phases"].append("uninstall preserves settings and leaves the running native process intact")
        await stop(native)
        native = await start(session_file)
        assert (await native.rpc("uninstalled", "get_state"))["data"]["sessionId"] == original_id
        commands = (await native.rpc("commands-final", "get_commands"))["data"]["commands"]
        assert not any(command["name"] == "xsm" for command in commands)
        assert "retained-session-context" in json.dumps((await native.rpc("context-final", "get_messages"))["data"])
        result["phases"].append("uninstalled profile resumes original context without xsm")
        result["status"] = "passed"
    except Exception as error:
        result.update(status="failed", error=repr(error))
    finally:
        if native and native.process.returncode is None:
            try:
                await stop(native)
            except Exception as error:
                result.update(status="failed", cleanupError=repr(error))
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    raise SystemExit(asyncio.run(run(options)))
