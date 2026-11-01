#!/usr/bin/env python3
"""Hermes 0.22.5's real plugin registry/hooks with caller fixtures, no agent/model claims."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
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
    (temp / "hermes/config.yaml").write_text("plugins:\n  enabled: false\n")
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
        binding = module.register(context)
        names = [name for name in manager._plugin_tool_names if name.startswith("xsm_")]
        assert len(names) == 21, names
        result["checks"].append("21 tools registered by actual PluginContext")
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
        tokens = set_session_vars(platform="tui", session_id="native-b", session_key="native-b", cwd=str(temp / "b"))
        try:
            forged = json.loads(registry.dispatch("xsm_inbox", {}, scope=manager.scope_key, session_id="native-a"))
            assert "differs" in str(forged), forged
        finally:
            clear_session_vars(tokens)
        result["checks"].append("mismatched native dispatcher identity is refused")
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
        result.update(status="passed", nativeTools=sorted(names), records=self_records)
    except BaseException as error:
        result.update(status="failed", error=repr(error))
        raise
    finally:
        if binding:
            binding.close()
        checkpoint()
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), "tag": tag}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
