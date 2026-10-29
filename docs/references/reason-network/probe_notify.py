#!/usr/bin/env python3
"""격리 엔진과 지연·실패하는 가짜 OS 알림으로 영수증의 증거 강도를 관찰한다."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from probe_engine import Client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="rn-notify-", dir="/private/tmp"))
    state = root / "state"
    state.mkdir()
    (state / "config.toml").write_text('person = "fixture"\nlan = false\ntray = false\nreason = false\nauto_update = false\n')
    fake = root / "fake-notify.py"
    fake.write_text("#!/usr/bin/env python3\nimport pathlib,os,time,sys\np=pathlib.Path(os.environ['FIXTURE_NOTIFY_ROOT'])\n(p/'started').write_text(str(time.time()))\nwhile not (p/'release').exists(): time.sleep(.02)\n(p/'failed').write_text('fixture notification rejected')\nprint('fixture notification rejected',file=sys.stderr)\nsys.exit(1)\n")
    fake.chmod(0o755)
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("CLAUDE", "CODEX", "REASON_NETWORK", "TINCAN")) or key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(key, None)
    env.update(REASON_NETWORK_HOME=str(state), REASON_NETWORK_NO_TRAY="1", REASON_NETWORK_NO_SERVICE="1", REASON_NETWORK_NO_MDNS="1", REASON_NETWORK_NO_UPDATE="1", REASON_NETWORK_OSASCRIPT_BIN=str(fake), FIXTURE_NOTIFY_ROOT=str(root), CLAUDE_CONFIG_DIR=str(root / "claude"), CODEX_HOME=str(root / "codex"))
    results = []
    daemon = client = None
    log_path = root / "daemon.log"
    log = log_path.open("w")

    def check(name, passed, detail):
        results.append(dict(name=name, passed=bool(passed), detail=detail))
        if not passed:
            raise AssertionError(name)

    def wait_for(predicate):
        until = time.monotonic() + 10
        while time.monotonic() < until:
            if predicate():
                return True
            time.sleep(.02)
        return False

    try:
        daemon = subprocess.Popen([str(args.engine.resolve()), "daemon"], env=env, cwd=root, stdout=log, stderr=log)
        assert wait_for(lambda: (state / "network.sock").exists())
        client = Client(state / "network.sock")
        registered = client.call("register", session=dict(key="fixture:sender", agent="fixture", cwd=str(root), tier="pull", name="sender"))
        assert registered["ok"]
        response = client.call("send", **{"from": "fixture:sender", "to": "fixture", "body": "FIXTURE_NOTIFY_ONLY", "notify": True})
        encoded = json.dumps(response)
        check("receipt-precedes-system-command-completion", response["ok"] and "popped up for fixture" in encoded and not (root / "failed").exists(), response)
        assert wait_for(lambda: (root / "started").exists())
        check("fake-notification-command-is-still-waiting", not (root / "failed").exists(), "실제 OS 알림 대신 파일 장벽에서 대기하는 fixture")
        (root / "release").touch()
        assert wait_for(lambda: "notification failed: fixture notification rejected" in log_path.read_text())
        check("later-command-failure-only-appears-in-daemon-log", (root / "failed").exists(), "notification failed: fixture notification rejected")
        again = client.call("send", **{"from": "fixture:sender", "to": "fixture", "body": "FIXTURE_NOTIFY_AGAIN", "notify": True})
        check("failed-command-still-occupies-person-rate-limit", again["ok"] and "had one from fixture" in json.dumps(again), again)
    except Exception as exc:
        results.append(dict(name="exception", passed=False, detail=f"{type(exc).__name__}: {exc}"))
    finally:
        (root / "release").touch()
        if client:
            client.close()
        if daemon is not None and daemon.poll() is None:
            daemon.terminate()
            daemon.wait(timeout=10)
        log.close()
        payload = dict(fixture_root=str(root), engine=str(args.engine.resolve()), results=results, passed=all(x["passed"] for x in results), real_os_notifications=0, process_stopped=daemon is None or daemon.poll() is not None)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(dict(passed=payload["passed"], cases=len(results))))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
