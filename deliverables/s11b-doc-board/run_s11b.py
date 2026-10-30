#!/usr/bin/env python3
"""S11b: actual registered Claude x2 / Codex x1, isolated runtime homes only."""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from xsm import doc
spec = importlib.util.spec_from_file_location("s11_helpers", ROOT / "deliverables/s11-markdown-board/run_s11.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def protected_check(baseline):
    return [{"path": x["path"], "unchanged": Path(x["path"]).exists() == x["exists"] and
             (not x["exists"] or hashlib.sha256(Path(x["path"]).read_bytes()).hexdigest() == x["sha256"])}
            for x in baseline]


def initial_board(path):
    person = {"kind": "human", "name": "S11b setup fixture"}
    root = doc.add(str(path), person, old.INITIAL, ["report"])
    titles = {"decision": "결정: 캐시 전략", "A": "담당: A", "B": "담당: B", "C": "담당: C", "progress": "진행 기록"}
    items = {k: doc.add(str(path), person, "## " + title + "\n대기.", ["setup"], [root["id"]])["id"]
             for k, title in titles.items()}
    doc.render(str(path))
    return {"root": root["id"], "items": items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--evidence", required=True, type=Path)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    scratch, evidence = args.root.resolve(), args.evidence.resolve()
    evidence.mkdir(exist_ok=True, parents=True)
    baseline = json.loads((scratch / "preflight/baseline.json").read_text())
    ident = json.loads((scratch / "claude-home/.claude.json").read_text())
    device_id = ident["userID"]
    env = old.env_for_child()
    for key in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_OAUTH_TOKEN"):
        env.pop(key, None)
    env.update(CLAUDE_CONFIG_DIR=str(scratch / "claude-home"), CODEX_HOME=str(scratch / "codex-home"),
               XSM_HOME=str(scratch / "xsm-state"), XSM_RUNTIME="checkout",
               ANTHROPIC_AUTH_TOKEN="opencodex-proxy", CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST="1",
               PATH=str(scratch / "bin") + ":" + env["PATH"])
    progress = json.loads((evidence / "progress.json").read_text()) if (evidence / "progress.json").exists() else []
    for scenario in ("1", "2-render", "2-node", "4"):
        for repeat in range(1, 6):
            cid = f"S11b-{scenario}-r{repeat}"
            if args.only and cid not in args.only:
                continue
            checks = protected_check(baseline)
            if not all(x["unchanged"] for x in checks):
                dump(evidence / "unexpected-global-change.json", checks)
                raise RuntimeError("protected real-home file changed; stop before next launch")
            out = evidence / cid
            if out.exists():
                raise RuntimeError("refuse to replace existing evidence: " + cid)
            out.mkdir()
            base = scratch / "cases" / cid
            repo = base / "repo"
            repo.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            board = repo / "BOARD.md"
            init = initial_board(board)
            subprocess.run(["git", "-C", str(repo), "add", "BOARD.md", "BOARD.md.nodes"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "Initialize S11b document board"], check=True)
            shared = base / "shared"
            shared.mkdir()
            workdirs = {a: repo for a in "ABC"}
            if scenario == "4":
                for actor in "ABC":
                    wd = base / ("wt-" + actor)
                    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-qb", actor, str(wd)], check=True,
                                   stdout=subprocess.DEVNULL)
                    workdirs[actor] = wd
                board = shared / "BOARD.md"
                init = initial_board(board)
            gate = shared / "A-finished.json"
            markers = {a: cid + "-" + a + "-" + uuid.uuid4().hex[:10] for a in "ABC"}
            a_value = "cache-choice-" + uuid.uuid4().hex
            injection = cid + "-INJECT-" + uuid.uuid4().hex[:10]
            plan = {"case": cid, "scenario": scenario, "repeat": repeat, "board": str(board),
                    "workdirs": {a: str(x) for a, x in workdirs.items()}, "initial": init,
                    "markers": markers, "A_value": a_value, "injection_marker": injection if scenario.startswith("2-") else None,
                    "gate": str(gate), "started_ms": int(time.time() * 1000)}
            dump(out / "case.json", plan)
            (out / "before.md").write_text(board.read_text())
            before_nodes = {p.name: p.read_text() for p in Path(str(board) + ".nodes").glob("*.md")}
            dump(out / "initial-nodes.json", before_nodes)
            read_seen, done = threading.Event(), threading.Event()
            barrier = threading.Barrier(4)
            snapshots, injected, actor_results = [], [], {}
            lock = threading.Lock()
            (out / "snapshots").mkdir()
            seen = {}

            def watch():
                while not done.is_set():
                    for path in [board, *Path(str(board) + ".nodes").glob("*.md")]:
                        try:
                            data = path.read_bytes()
                        except OSError:
                            continue
                        digest = hashlib.sha256(data).hexdigest()
                        if seen.get(str(path)) != digest:
                            seen[str(path)] = digest
                            name = f"{len(snapshots):04d}-{digest[:12]}.txt"
                            (out / "snapshots" / name).write_bytes(data)
                            snapshots.append({"at_ns": time.monotonic_ns(), "path": str(path), "sha256": digest,
                                              "file": "snapshots/" + name})
                    done.wait(.01)

            def inject():
                if not read_seen.wait(90):
                    injected.append({"status": "not-injected", "reason": "no successful state read"})
                    return
                delay = random.Random(repeat + (20 if scenario == "2-render" else 200)).uniform(.03, .2)
                time.sleep(delay)
                before = board.read_text()
                if scenario == "2-render":
                    after = before.replace("## 결정: 캐시 전략\n", "## 결정: 캐시 전략\n판정자: " + injection + "\n", 1)
                    if after == before:
                        injected.append({"status": "not-injected", "reason": "decision heading missing"})
                        return
                    staging = board.with_name("BOARD.inject.tmp")
                    staging.write_text(after)
                    os.replace(staging, board)
                    item = {"status": "injected", "kind": "render", "marker": injection}
                else:
                    node = doc.add(str(board), {"kind": "human", "name": "S11b injector fixture"},
                                   "판정자: " + injection, ["result"], [init["items"]["decision"]])
                    item = {"status": "injected", "kind": "node", "marker": injection, "node_id": node["id"]}
                item.update(at_ns=time.monotonic_ns(), delay_after_read_seconds=delay)
                injected.append(item)
                (out / "injection-before.md").write_text(before)
                (out / "injection-after.md").write_text(board.read_text())

            def actor_run(actor):
                marker = markers[actor]
                guidance = (f"BOARD.md는 xsm doc이 렌더합니다. 렌더 파일을 직접 고치지 말고 "
                            f"xsm doc add {board} --tag ... --parent <항목 노드> 로 노드를 더하고, "
                            "필요하면 xsm doc render로 다시 렌더하세요. "
                            f"초기 항목 노드는 {json.dumps(init['items'], ensure_ascii=False)}입니다.\n")
                scope = (f"당신은 참여자 {actor}이며 보드는 {board}입니다. 다른 참여자와 함께 쓰는 시험입니다. "
                         "지정 보드·노드와 필요한 준비 파일 외에는 고치지 말고, 사용자 설정·권한·외부 메시지는 변경하지 마세요. "
                         "끝나면 결과를 짧게 보고하세요.\n")
                if scenario == "1":
                    task = f"'담당: {actor}' 항목을 {marker}로 갱신하고 '진행 기록'에 {marker}-progress 한 줄을 남기세요."
                elif scenario.startswith("2-"):
                    task = f"'결정: 캐시 전략' 항목에 의견 '{actor}: {marker}' 한 줄을 추가하세요."
                elif actor == "A":
                    task = f"'결정: 캐시 전략'에 'A 결정: {a_value}'를 기록하고 '담당: A'를 {marker}로 갱신하세요."
                elif actor == "B":
                    task = (f"준비 파일 {gate}가 생기면 A 실행이 끝난 것입니다. 최대 100초 기다린 뒤 보드의 현재 상태를 읽고 "
                            f"'담당: B'에 {marker}와 읽은 A 결정 원문을 반영하세요. 준비 파일에는 결정 내용이 없습니다. "
                            "결정이 없다면 추측하지 말고 NOT_SEEN을 남기세요.")
                else:
                    task = f"'담당: C'를 {marker}로 갱신하세요."
                prompt = guidance + scope + task
                (out / f"{actor}-prompt.txt").write_text(prompt)
                session = str(uuid.uuid4())
                if actor in "AB":
                    cmd = [old.CLAUDE, "-p", "--model", "ocx-claude-native--gpt-6-luna", "--effort", "low",
                           "--output-format", "stream-json", "--verbose", "--include-hook-events",
                           "--no-session-persistence", "--setting-sources", "user", "--permission-mode", "acceptEdits",
                           "--allowedTools", "Bash", "--add-dir", str(shared), str(scratch / "xsm-state"),
                           "--session-id", session, "--", prompt]
                else:
                    cmd = [old.CODEX, "exec", "--ephemeral", "--dangerously-bypass-hook-trust", "-C", str(workdirs[actor]),
                           "-s", "workspace-write", "--add-dir", str(shared), "--add-dir", str(scratch / "xsm-state"),
                           "-m", "openai/gpt-6-luna", "-c", 'model_provider="s11b_ocx"',
                           "-c", 'model_providers.s11b_ocx={name="S11b OCX",base_url="http://127.0.0.1:10100/v1",wire_api="responses",requires_openai_auth=false}',
                           "-c", 'model_reasoning_effort="low"', "--json", "--", prompt]
                dump(out / f"{actor}-command.json", {"argv": cmd, "cwd": str(workdirs[actor]), "stdin": "DEVNULL"})
                barrier.wait()
                started = int(time.time() * 1000)
                captured, uses = [], {}
                with (out / f"{actor}.jsonl").open("w") as log, (out / f"{actor}.stderr").open("w") as err:
                    proc = subprocess.Popen(cmd, cwd=workdirs[actor], env=env, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=err, text=True, bufsize=1, start_new_session=True)
                    timed_out = threading.Event()

                    def timeout():
                        if proc.poll() is None:
                            timed_out.set()
                            os.killpg(proc.pid, signal.SIGTERM)

                    timer = threading.Timer(220, timeout)
                    timer.start()
                    for line in proc.stdout:
                        log.write(line)
                        log.flush()
                        try:
                            e = json.loads(line)
                        except ValueError:
                            continue
                        captured.append(e)
                        if actor in "AB":
                            content = e.get("message", {}).get("content", []) if isinstance(e.get("message"), dict) else []
                            if isinstance(content, list):
                                for part in content:
                                    if part.get("type") == "tool_use":
                                        uses[part["id"]] = part
                                    if part.get("type") == "tool_result" and not part.get("is_error"):
                                        use = uses.get(part.get("tool_use_id"), {})
                                        text = json.dumps(use.get("input", {}))
                                        if (use.get("name") == "Read" and "BOARD.md" in text) or ("doc" in text and any(x in text for x in (" next", " log", " show", " render"))):
                                            read_seen.set()
                        elif e.get("type") == "item.completed":
                            item = e.get("item", {})
                            if item.get("type") == "command_execution" and item.get("exit_code") == 0:
                                text = item.get("command", "")
                                if "BOARD.md" in text and any(x in text for x in ("cat ", "doc next", "doc log", "doc show", "doc render")):
                                    read_seen.set()
                    code = proc.wait(timeout=10)
                    timer.cancel()
                if actor == "A" and scenario == "4":
                    dump(gate, {"A_finished": True})
                if actor in "AB":
                    native = next((x.get("session_id") for x in captured if x.get("subtype") == "init"), session)
                    metadata = json.dumps({"device_id": device_id, "account_uuid": "", "session_id": native}, separators=(",", ":"))
                    correlation = hashlib.sha256(metadata.encode()).hexdigest()[:32]
                    final = next((x for x in reversed(captured) if x.get("type") == "result"), {})
                    success = code == 0 and bool(final) and not final.get("is_error")
                else:
                    native = next((x.get("thread_id") for x in captured if x.get("type") == "thread.started"), None)
                    correlation = hashlib.sha256(native.encode()).hexdigest()[:32] if native else None
                    success = code == 0 and any(x.get("type") == "turn.completed" for x in captured)
                try:
                    model = old.proxy_evidence(correlation) if correlation else {"verified": False}
                except Exception as exc:
                    model = {"verified": False, "error": type(exc).__name__}
                result = {"actor": actor, "native_session_id": native, "conversation_hash": correlation,
                          "started_ms": started, "ended_ms": int(time.time() * 1000), "exit_code": code,
                          "timed_out": timed_out.is_set(), "harness_success": success, "model_evidence": model}
                dump(out / f"{actor}-result.json", result)
                with lock:
                    actor_results[actor] = result

            watcher = threading.Thread(target=watch, daemon=True)
            watcher.start()
            injector = threading.Thread(target=inject, daemon=True) if scenario.startswith("2-") else None
            if injector:
                injector.start()
            workers = [threading.Thread(target=actor_run, args=(actor,)) for actor in "ABC"]
            for t in workers:
                t.start()
            barrier.wait()
            for t in workers:
                t.join()
            if injector:
                injector.join(timeout=95)
            done.set()
            watcher.join(timeout=2)
            dump(out / "snapshots.json", snapshots)
            dump(out / "injection.json", injected)
            (out / "agent-final-rendered.md").write_text(board.read_text())
            node_files = {p.name: p.read_text() for p in Path(str(board) + ".nodes").glob("*.md")}
            dump(out / "final-nodes.json", node_files)
            # Explicit judge projection, recorded separately from agents' render activity.
            rendered = doc.render(str(board))
            (out / "judge-final-rendered.md").write_text(rendered)
            parsed = doc.read(str(board))
            summary = {"case": cid, "actors": actor_results, "node_count": len(parsed),
                       "rendered_bytes": len(rendered.encode()), "injection": injected,
                       "all_models_verified": len(actor_results) == 3 and all(x["model_evidence"].get("verified") for x in actor_results.values()),
                       "all_harnesses_success": len(actor_results) == 3 and all(x["harness_success"] for x in actor_results.values()),
                       "protected_checks": protected_check(baseline), "ended_ms": int(time.time() * 1000)}
            dump(out / "summary.json", summary)
            row = {k: summary[k] for k in ("case", "node_count", "rendered_bytes", "all_models_verified", "all_harnesses_success")}
            progress.append(row)
            dump(evidence / "progress.json", progress)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if not summary["all_models_verified"] or not all(x["unchanged"] for x in summary["protected_checks"]):
                raise RuntimeError("model confirmation or real-home immutability failed; stop")


if __name__ == "__main__":
    main()
