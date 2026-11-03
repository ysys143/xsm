#!/usr/bin/env python3
"""Hermes 0.22.5's real plugin registry/hooks with caller fixtures, no agent/model claims."""
import argparse
import concurrent.futures
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import signal
import time
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="xsm-hermes-tools-"))
    env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR") if key in os.environ}
    env.update(HOME=str(temp / "home"), HERMES_HOME=str(temp / "hermes"), XSM_HOME=str(temp / "state"),
               PYTHONDONTWRITEBYTECODE="1")
    os.environ.clear()
    os.environ.update(env)
    for name in ("home", "hermes", "a", "b"):
        (temp / name).mkdir()
    subprocess.run(["git", "init", "-q", str(temp)], env=env, check=True)
    # Keep unrelated bundled discovery out of this API probe; register through the actual facade below.
    (temp / "hermes/config.yaml").write_text("plugins:\n  enabled: [xsm]\n" if args.discover else "plugins:\n  enabled: false\n")
    if args.installed:
        args.discover = True
        (temp / "hermes/config.yaml").write_text("plugins:\n  enabled: [xsm]\n")
        sys.path.insert(0, str(ROOT))
        from xsm import host_install
        installed = host_install.apply("hermes", str(temp / "hermes"))
    elif args.discover:
        folder = temp / "hermes/plugins"
        folder.mkdir()
        (folder / "xsm").symlink_to(ROOT / "integrations/hermes", target_is_directory=True)
    source = args.native_source.resolve()
    tag = subprocess.run(["git", "describe", "--tags", "--exact-match"], cwd=source,
                         env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert tag == "v0.22.5", tag
    sys.path.insert(0, str(source))
    from hermes_cli import plugins
    from hermes_cli.plugins_manifest import PluginManifest
    from gateway.session_context import set_session_vars, clear_session_vars
    from tools.registry import registry
    assert Path(plugins.__file__).resolve().is_relative_to(source)
    manager = plugins.get_plugin_manager()
    context = plugins.PluginContext(PluginManifest(name="xsm", version="dev", source="user",
        path=str(ROOT / "integrations/hermes")), manager)
    spec = importlib.util.spec_from_file_location("native_xsm_hermes", ROOT / "integrations/hermes/xsm.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    binding = None
    result = {"status": "running", "root": str(temp), "tag": tag, "python": sys.version.split()[0],
        "nativePluginApiTested": True, "nativeAgentOrModelTested": False, "nativeAdmissionTested": False,
        "callerFixture": True, "checks": [], "sourceSha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("integrations/hermes/xsm.py", "clients/python/xsm_host.py", "scripts/probe-hermes-tools.py")}}

    if args.installed:
        result["installation"] = installed

    def checkpoint():
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def records():
        return [json.loads(path.read_text()) for path in (temp / "state/sessions").glob("*.json")]

    def invoke(sid, cwd, tool, args=None, **native):
        tokens = set_session_vars(platform="tui", session_key=sid, session_id=sid, cwd=str(cwd))
        try:
            return json.loads(registry.dispatch(tool, args or {}, scope=manager.scope_key,
                                                session_id=sid, **native))
        finally:
            clear_session_vars(tokens)

    checkpoint()
    try:
        if args.discover:
            manager.discover_and_load()
            loaded = manager._plugins.get("xsm")
            assert loaded and loaded.enabled, getattr(loaded, "error", "not discovered")
            result["nativeDiscoveryTested"] = True
        else:
            if args.slow_registration:
                release = temp / "release-slow-registration"
                entered = temp / "entered-slow-registration"
                code = ("import sys,time,pathlib,runpy;sys.path.insert(0,sys.argv[1]);from xsm import protocol\n"
                    "_open=protocol.Connection.open\n"
                    "def _slow(self,params):\n"
                    " if params.get('conversation')=='native-slow':\n"
                    "  pathlib.Path(" + repr(str(entered)) + ").touch()\n"
                    "  while not pathlib.Path(" + repr(str(release)) + ").exists(): time.sleep(.01)\n"
                    " return _open(self,params)\n"
                    "protocol.Connection.open=_slow\n"
                    "sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')")
                binding = module.register(context, command=[sys.executable, "-B", "-c", code, str(ROOT), "protocol", "serve", "--stdio"])
            else:
                binding = module.register(context)
        if args.installed:
            from xsm import component_leases
            live = component_leases.active_records()
            assert len(live) == 1 and live[0]["component"] == "hermes-plugin", live
            assert live[0]["pid"] == os.getpid()
            assert Path(live[0]["root"]).resolve() == Path(installed["runtime_root"]).resolve()
            host_install.remove("hermes", str(temp / "hermes"))
            assert str(Path(installed["runtime_root"]).resolve()) in component_leases.configured_roots()
            result["checks"].append("loaded native plugin retains its snapshot after owned files are removed")
        names = [name for name in manager._plugin_tool_names if name.startswith("xsm_")]
        assert len(names) == 22, names
        result["checks"].append("22 tools registered by actual PluginContext")
        for sid, cwd in (("native-a", temp / "a"), ("native-b", temp / "b")):
            tokens = set_session_vars(platform="tui", session_key=sid, session_id=sid, cwd=str(cwd))
            try:
                manager.invoke_hook("on_session_start", session_id=sid)
            finally:
                clear_session_vars(tokens)
        self_records = [item for item in records() if item["runtime"] == "hermes"]
        assert len(self_records) == 2, self_records
        first = next(item for item in self_records if item["cwd"] == str((temp / "a").resolve()))
        second = next(item for item in self_records if item["cwd"] == str((temp / "b").resolve()))
        assert first["ref"] != second["ref"]
        result["checks"].append("task-local native identities and workspaces stay separate")
        sent = invoke("native-a", temp / "a", "xsm_send", {"target": "ref:" + second["ref"], "text": "native registry fixture", "wait": 0})
        assert "stored" in sent["text"], sent
        packet = invoke("native-b", temp / "b", "xsm_inbox")
        assert len(packet["claims"]) == 1 and "native registry fixture" in str(packet), packet
        ack = invoke("native-b", temp / "b", "xsm_ack", {"tokens": [packet["claims"][0]["token"]]})
        assert len(ack["acked"]) == 1, ack
        result["checks"].append("native tool dispatch sends, pulls and explicitly ACKs")
        if args.slow_registration:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                slow = pool.submit(invoke, "native-slow", temp / "b", "xsm_inbox")
                fast = None
                try:
                    deadline = time.monotonic() + 3
                    while not entered.exists():
                        assert time.monotonic() < deadline, "slow registration did not start"
                        time.sleep(.01)
                    started = time.monotonic()
                    fast = pool.submit(invoke, "native-b", temp / "b", "xsm_inbox")
                    packet = fast.result(timeout=1)
                    assert packet["claims"] == [] and not slow.done(), packet
                    result["registrationIsolation"] = {"fastCompletedWhileOtherOpenBlocked": True,
                        "fastSeconds": time.monotonic() - started, "nativeDispatchers": 2}
                    result["checks"].append("native registry dispatch remains available while another backend registration is blocked")
                finally:
                    release.touch()
                    slow.result(timeout=5)
                    if fast:
                        fast.result(timeout=5)
        if args.crash or args.auto_reconnect:
            invoke("native-a", temp / "a", "xsm_send", {"target": "ref:" + second["ref"],
                   "text": "original survives backend crash", "wait": 0})
            claimed = invoke("native-b", temp / "b", "xsm_inbox")["claims"][0]
            before = next(item for item in records() if item["ref"] == second["ref"])
            parent = subprocess.run(["ps", "-o", "ppid=", "-p", str(before["pid"])],
                                    capture_output=True, text=True, check=True).stdout.strip()
            assert int(parent) == os.getpid(), "refuse to kill a process not created by this probe"
            os.kill(before["pid"], signal.SIGKILL)
            deadline = time.monotonic() + 5
            while True:
                try:
                    os.kill(before["pid"], 0)
                except ProcessLookupError:
                    break
                assert time.monotonic() < deadline, "backend process did not exit"
                time.sleep(.01)
            if args.auto_reconnect:
                automatic = None
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    automatic = next((item for item in records() if item.get("ref") == before["ref"] and
                        item.get("pid") != before["pid"] and not item.get("ended_at") and
                        item.get("activity") == before.get("activity")), None)
                    if automatic:
                        break
                    time.sleep(.01)
                assert automatic, "backend did not reconnect before native dispatch"
                result["automaticReconnectObservedBeforeNativeEntry"] = True
                result["checks"].append("automatic backend registration restores hook activity before native dispatch")
            recovered = invoke("native-b", temp / "b", "xsm_inbox")
            after = next(item for item in records() if item["ref"] == second["ref"])
            assert after["pid"] != before["pid"] and after["protocol_generation"] != before["protocol_generation"]
            assert recovered["claims"][0]["id"] == claimed["id"] and recovered["claims"][0]["token"] != claimed["token"]
            refused = invoke("native-b", temp / "b", "xsm_ack", {"tokens": [claimed["token"]]})
            assert "not owned" in str(refused) or "another owner or generation" in str(refused), refused
            acknowledged = invoke("native-b", temp / "b", "xsm_ack", {"tokens": [recovered["claims"][0]["token"]]})
            assert acknowledged["acked"] == [claimed["id"]], acknowledged
            result["backendRecovery"] = {"oldPid": before["pid"], "newPid": after["pid"],
                "ref": after["ref"], "generationChanged": True, "originalRecovered": True,
                "previousClaimRejected": True, "explicitAck": acknowledged["acked"]}
            result["checks"].append("next native dispatch recovers crashed backend with fresh generation and claim")
        tokens = set_session_vars(platform="tui", session_id="native-b", session_key="native-b", cwd=str(temp / "b"))
        try:
            forged = json.loads(registry.dispatch("xsm_inbox", {}, scope=manager.scope_key, session_id="native-a"))
            assert "workspace changed" in str(forged), forged
        finally:
            clear_session_vars(tokens)
        result["checks"].append("existing native caller cannot borrow another workspace")
        tokens = set_session_vars(platform="tui", session_id="native-a", session_key="native-a", cwd=str(temp / "b"))
        try:
            manager.invoke_hook("on_session_start", session_id="native-a")
        finally:
            clear_session_vars(tokens)
        moved = next(item for item in records() if item["ref"] == first["ref"])
        assert moved["cwd"] == str((temp / "b").resolve())
        assert moved["protocol_generation"] != first["protocol_generation"]
        invoke("native-a", temp / "b", "xsm_inbox")
        stale = invoke("native-a", temp / "a", "xsm_inbox")
        assert "workspace changed" in str(stale), stale
        result["checks"].append("native session-start workspace move keeps ref and replaces participation")
        manager.invoke_hook("on_session_end", session_id="native-a")
        assert not next(item for item in records() if item["ref"] == first["ref"]).get("ended_at")
        manager.invoke_hook("on_session_finalize", session_id="native-a")
        closed = next(item for item in records() if item["ref"] == first["ref"])
        assert closed.get("ended_at"), closed
        invoke("native-a", temp / "a", "xsm_inbox")
        resumed = next(item for item in records() if item["ref"] == first["ref"])
        assert resumed["protocol_generation"] != first["protocol_generation"]
        result["checks"].append("turn end stays live; finalize/resume keeps ref and rotates generation")
        unavailable = invoke("native-a", temp / "a", "xsm_decide", {"question": "Unbound UI must not answer"})
        assert "no user-interface" in str(unavailable), unavailable
        result["checks"].append("unbound native user UI records no approval")
        if args.discover:
            manager.unload("xsm")
            assert all(registry.get_entry(name, scope=manager.scope_key) is None for name in names)
            assert all(item.get("ended_at") for item in records() if item["runtime"] == "hermes")
            result["checks"].append("native unload removes tools and closes every participation")
        if args.installed:
            assert all(Path(item["protocol_root"]).resolve() == Path(installed["runtime_root"]).resolve()
                       for item in self_records)
            assert component_leases.active_records() == []
            assert list((temp / "state/component-leases").glob("*.json")) == []
            result["checks"].append("native unload releases the component snapshot lease")
            config_before = (temp / "hermes/config.yaml").read_bytes()
            host_install.remove("hermes", str(temp / "hermes"))
            assert not (temp / "hermes/plugins/xsm/__init__.py").exists()
            assert not (temp / "hermes/plugins/xsm/plugin.yaml").exists()
            assert (temp / "hermes/config.yaml").read_bytes() == config_before
            result["checks"].append("owned snapshot backend and uninstall preserve operator configuration")
        result.update(status="passed", nativeTools=sorted(names), records=self_records)
    except BaseException as error:
        result.update(status="failed", error=repr(error))
        raise
    finally:
        if binding:
            binding.close()
        if args.discover:
            manager.unload("xsm")
        checkpoint()
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), "tag": tag}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--crash", action="store_true")
    parser.add_argument("--auto-reconnect", action="store_true")
    parser.add_argument("--slow-registration", action="store_true")
    args = parser.parse_args()
    if args.slow_registration and (args.installed or args.discover):
        parser.error("--slow-registration uses the explicit native PluginContext fixture")
    run(args)
