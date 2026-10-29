#!/usr/bin/env python3
"""합성 두 대화가 공유하는 MCP의 식별·첨부 루트를 관찰한다. 실제 하네스 재현과 구분한다."""
import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
from probe_engine import Client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="rn-mcp-", dir="/private/tmp")).resolve()
    state = root / "state"
    state.mkdir()
    (state / "config.toml").write_text('person = "fixture"\nlan = false\ntray = false\nauto_update = false\n')
    a, b = root / "repo-a", root / "repo-b"
    a.mkdir(); b.mkdir()
    (a / "sample.txt").write_text("SAMPLE_A\n")
    (b / "sample.txt").write_text("SAMPLE_B\n")
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("CLAUDE", "CODEX", "REASON_NETWORK", "TINCAN")) or key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(key, None)
    env.update(REASON_NETWORK_HOME=str(state), REASON_NETWORK_NO_TRAY="1", REASON_NETWORK_NO_SERVICE="1", REASON_NETWORK_NO_MDNS="1", CLAUDE_CONFIG_DIR=str(root / "claude"), CODEX_HOME=str(root / "codex"))
    results = []
    daemon = mcp = ipc = None
    log = (root / "processes.log").open("w")
    seq = 0

    def rpc(method, params):
        nonlocal seq
        seq += 1
        mcp.stdin.write(json.dumps(dict(jsonrpc="2.0", id=seq, method=method, params=params)) + "\n")
        mcp.stdin.flush()
        until = time.monotonic() + 15
        while time.monotonic() < until:
            if not select.select([mcp.stdout], [], [], max(0, until - time.monotonic()))[0]:
                break
            line = mcp.stdout.readline()
            if not line:
                raise RuntimeError("MCP closed")
            value = json.loads(line)
            if value.get("id") == seq:
                return value
        raise TimeoutError(method)

    def tool(name, arguments, session):
        return rpc("tools/call", dict(name=name, arguments=arguments, _meta=dict(sessionId=session)))

    def check(name, passed, observed):
        results.append(dict(name=name, passed=bool(passed), observed=observed))
        if not passed:
            raise AssertionError(name)

    try:
        daemon = subprocess.Popen([str(args.engine.resolve()), "daemon"], cwd=a, env=env, stdout=log, stderr=log)
        for _ in range(100):
            if (state / "network.sock").exists():
                break
            time.sleep(.05)
        ipc = Client(state / "network.sock")
        receiver = ipc.call("register", session=dict(key="fixture:receiver", agent="fixture", cwd=str(b), tier="pull", name="receiver"))
        mcp = subprocess.Popen([str(args.engine.resolve()), "mcp"], cwd=a, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
        init = rpc("initialize", dict(protocolVersion="2025-06-18", capabilities={}, clientInfo=dict(name="codex-mcp-client", version="fixture")))
        mcp.stdin.write(json.dumps(dict(jsonrpc="2.0", method="notifications/initialized")) + "\n"); mcp.stdin.flush()
        tools = rpc("tools/list", {})
        schema = next(t for t in tools["result"]["tools"] if t["name"] == "send_message")["inputSchema"]["properties"]
        check("send-schema-has-files-but-no-fyi", "files" in schema and "fyi" not in schema and "wake" not in schema, list(schema))
        first = tool("list_team", {}, "synthetic-a")
        hook = ipc.call("hook", agent="codex", event="prompt", session_id="synthetic-b", cwd=str(b), pid=os.getpid(), mail=False)
        second = tool("list_team", {}, "synthetic-b")
        rows = ipc.call("who", me="codex:synthetic-b")["result"]["sessions"]
        mine = [r for r in rows if r["is_me"]]
        shown = "\n".join(x.get("text", "") for x in second.get("result", {}).get("content", []))
        marked = [line for line in shown.splitlines() if "← you" in line]
        def marks_folder(lines, folder):
            return len(lines) == 1 and folder in lines[0]
        # 잘못된 A 호출자 표시를 넣으면 B 식별 검사가 실패해야 한다.
        assert not marks_folder(["repo-a-codex repo-a ← you"], "repo-b")
        assert marks_folder(["repo-b-codex repo-b ← you"], "repo-b")
        check("shared-mcp-identifies-second-conversation", len(mine) == 1 and mine[0]["cwd"] == str(b) and marks_folder(marked, "repo-b"), dict(caller=mine, first=first, second=second, hook=hook))
        own = tool("send_message", dict(to="fixture/receiver", message="ATTACHMENT_A", files=[str(a / "sample.txt")]), "synthetic-a")
        check("process-folder-attachment-succeeds", not own.get("error") and not own["result"].get("isError", False), own)
        other = tool("send_message", dict(to="fixture/receiver", message="ATTACHMENT_B", files=[str(b / "sample.txt")]), "synthetic-b")
        text = json.dumps(other, ensure_ascii=False)
        check("second-conversation-folder-is-rejected-by-process-root", other["result"].get("isError", False) and "outside this session" in text and str(a) in text, other)
        inbox = ipc.call("inbox", key="fixture:receiver", peek=True)
        messages = inbox["result"]["messages"]
        check("only-first-attachment-arrives", len(messages) == 1 and messages[0]["body"] == "ATTACHMENT_A" and len(messages[0].get("files", [])) == 1, inbox)
    except Exception as exc:
        results.append(dict(name="probe-exception", passed=False, error=f"{type(exc).__name__}: {exc}"))
    finally:
        if ipc is not None:
            ipc.close()
        for process in (mcp, daemon):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        log.close()
        payload = dict(engine=str(args.engine.resolve()), state=str(root), fixture=True, native_harness_process_sharing_verified=False, defect_scope="one synthetic MCP process; two call session IDs and distinct hook cwd", results=results, passed=all(r["passed"] for r in results), processes_stopped=all(p is None or p.poll() is not None for p in (mcp, daemon)))
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(dict(passed=payload["passed"], cases=len(results), output=str(args.output))))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
