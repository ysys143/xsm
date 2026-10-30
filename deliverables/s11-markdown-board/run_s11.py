#!/usr/bin/env python3
"""S11 local experiment runner. Only scratch repositories and this evidence directory."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import threading
import time
import uuid

CLAUDE = "/Users/jaesolshin/.local/bin/claude"
CODEX = "/Users/jaesolshin/.nvm/versions/node/v24.19.0/bin/codex"
OCX = "/Users/jaesolshin/.nvm/versions/node/v24.19.0/bin/ocx"
INITIAL = """# 공동 작업 보드

## 결정: 캐시 전략
아직 결정 없음.

## 담당: A
대기.

## 담당: B
대기.

## 담당: C
대기.

## 진행 기록
실험 시작.
"""


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def events(path):
    result = []
    if not path.exists():
        return result
    for line in path.read_text(errors="replace").splitlines():
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result


def env_for_child():
    env = os.environ.copy()
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY",
                "OPENROUTER_API_KEY", "CLAUDECODE"):
        env.pop(key, None)
    env["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:10100"
    env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = "1"
    return env


def argv_for(actor, cwd, extra, prompt, session_id):
    if actor in ("A", "B"):
        args = [CLAUDE, "-p", "--model", "ocx-claude-native--gpt-6-luna",
                "--effort", "low", "--output-format", "stream-json", "--verbose",
                "--include-partial-messages", "--no-session-persistence", "--safe-mode",
                "--setting-sources", "", "--strict-mcp-config", "--mcp-config",
                '{"mcpServers":{}}', "--permission-mode", "acceptEdits",
                "--session-id", session_id]
        for directory in extra:
            args += ["--add-dir", str(directory)]
        return args + ["--", prompt]
    args = [CODEX, "exec", "--ignore-user-config", "--ephemeral", "-C", str(cwd),
            "-s", "workspace-write", "-m", "openai/gpt-6-luna",
            "-c", 'model_provider="s11_ocx"',
            "-c", 'model_providers.s11_ocx={name="S11 OCX",base_url="http://127.0.0.1:10100/v1",wire_api="responses",requires_openai_auth=true}',
            "-c", 'model_reasoning_effort="low"', "--json"]
    for directory in extra:
        args += ["--add-dir", str(directory)]
    return args + ["--", prompt]


def proxy_evidence(conversation):
    cmd = [OCX, "observe", "logs", "--conversation", conversation, "--limit", "200", "--json"]
    run = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25)
    if run.returncode:
        return {"query_exit": run.returncode, "rows": [], "verified": False}
    data = json.loads(run.stdout)
    rows = []
    for row in data.get("logs", []):
        rows.append({**{k: row.get(k) for k in ("requestId", "timestamp", "conversationId",
                     "model", "requestedModel", "resolvedModel", "servedModel", "provider",
                     "status", "inboundProtocol", "terminalStatus", "usageStatus")},
                     "attempts": [{k: a.get(k) for k in ("provider", "model", "status", "ordinal")}
                                  for a in row.get("attempts", [])]})
    served = [r for r in rows if r.get("servedModel")]
    valid = bool(served) and all(r["servedModel"] == "gpt-6-luna" and r["provider"] == "openai"
                                 and all(a.get("model") == "gpt-6-luna" and a.get("provider") == "openai"
                                         for a in r["attempts"]) for r in served)
    return {"query_exit": 0, "rows": rows, "verified": valid,
            "scope": "conversation hash matches native session metadata; selected proxy fields only, no credentials"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--evidence", required=True, type=Path)
    ap.add_argument("--only", nargs="*", help="case IDs, e.g. S11-1-r1")
    args = ap.parse_args()
    scratch, evidence = args.scratch.resolve(), args.evidence.resolve()
    scratch.mkdir(exist_ok=True, parents=True)
    evidence.mkdir(exist_ok=True, parents=True)
    # Read only non-secret identity metadata for the proxy's documented hashing convention.
    identity_path = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / ".claude.json"
    ident = json.loads(identity_path.read_text())
    device_id = ident["userID"]
    account_uuid = ident["oauthAccount"]["accountUuid"]
    all_results = json.loads((evidence / "progress.json").read_text()) if (evidence / "progress.json").exists() else []
    env = env_for_child()
    for scenario in range(1, 5):
        for repeat in range(1, 6):
            cid = f"S11-{scenario}-r{repeat}"
            if args.only and cid not in args.only:
                continue
            out = evidence / cid
            if out.exists():
                raise RuntimeError(f"refuse to overwrite evidence: {out}")
            out.mkdir()
            base = scratch / cid
            repo = base / "repo"
            repo.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "BOARD.md").write_text(INITIAL)
            (out / "before.md").write_text(INITIAL)
            subprocess.run(["git", "-C", str(repo), "add", "BOARD.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "Initialize S11 board"], check=True)
            if scenario in (3, 4):
                workdirs = {}
                for actor in "ABC":
                    wd = base / ("wt-" + actor)
                    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-qb", actor, str(wd)], check=True,
                                   stdout=subprocess.DEVNULL)
                    workdirs[actor] = wd
            else:
                workdirs = {a: repo for a in "ABC"}
            shared = base / "shared"
            shared.mkdir()
            gate = shared / "A-finished.json"
            if scenario == 4:
                (shared / "BOARD.md").write_text(INITIAL)
                boards = {a: shared / "BOARD.md" for a in "ABC"}
            else:
                boards = {a: workdirs[a] / "BOARD.md" for a in "ABC"}
            expected = {a: f"{cid}-{a}-{uuid.uuid4().hex[:12]}" for a in "ABC"}
            a_decision = "cache-choice-" + uuid.uuid4().hex
            injected = f"{cid}-INJECT-{uuid.uuid4().hex[:12]}"
            plan = {"case": cid, "scenario": scenario, "repeat": repeat, "started_at": stamp(),
                    "workdirs": {a: str(p) for a, p in workdirs.items()},
                    "boards": {a: str(p) for a, p in boards.items()}, "markers": expected,
                    "A_decision": a_decision, "gate": str(gate), "injection_marker": injected if scenario == 2 else None,
                    "note": "A decision value is only in A's prompt. B/C prompts and gate contain no oracle."}
            write_json(out / "case.json", plan)
            launch_barrier = threading.Barrier(4)
            state_lock = threading.Lock()
            read_seen = threading.Event()
            stop_watch = threading.Event()
            actor_results = {}
            snapshots = []
            snapshot_seen = {}
            injected_record = []
            (out / "snapshots").mkdir()

            def snapshot_loop():
                while not stop_watch.is_set():
                    for path in set(boards.values()):
                        try:
                            data = path.read_bytes()
                        except OSError:
                            continue
                        digest = hashlib.sha256(data).hexdigest()
                        if snapshot_seen.get(str(path)) != digest:
                            snapshot_seen[str(path)] = digest
                            idx = len(snapshots)
                            name = f"{idx:04d}-{digest[:12]}.md"
                            (out / "snapshots" / name).write_bytes(data)
                            snapshots.append({"monotonic_ns": time.monotonic_ns(), "path": str(path),
                                              "sha256": digest, "file": "snapshots/" + name})
                    stop_watch.wait(.005)

            def inject():
                if not read_seen.wait(80):
                    injected_record.append({"status": "not-injected", "reason": "no successful board read observed"})
                    return
                delay = random.Random(scenario * 1000 + repeat).uniform(.03, .2)
                time.sleep(delay)
                p = boards["A"]
                before = p.read_text()
                after = before.replace("## 결정: 캐시 전략\n", "## 결정: 캐시 전략\n판정자: " + injected + "\n", 1)
                staged = p.with_name("BOARD.inject.tmp")
                staged.write_text(after)
                os.replace(staged, p)
                injected_record.append({"status": "injected", "at": stamp(), "monotonic_ns": time.monotonic_ns(),
                                        "delay_after_read_seconds": delay, "marker": injected,
                                        "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                                        "after_sha256": hashlib.sha256(after.encode()).hexdigest()})
                (out / "injection-before.md").write_text(before)
                (out / "injection-after.md").write_text(after)

            def actor_run(actor):
                marker = expected[actor]
                board = boards[actor]
                common = (f"공동 작업 보드 {board}를 다른 참여자와 함께 쓰고 있습니다. "
                          f"당신은 참여자 {actor}입니다. 지정된 보드와 필요한 준비 파일 외의 자료를 읽거나 고치지 마세요. "
                          "사용자 프로젝트·설정·권한을 변경하거나 외부 메시지를 보내지 마세요. 작업을 끝내고 결과를 짧게 보고하세요.\n")
                if scenario == 1:
                    task = f"보드의 '담당: {actor}' 항목을 '{marker}'로 갱신하고, '진행 기록'에 '{marker}-progress' 한 줄을 추가하세요."
                elif scenario == 2:
                    task = f"'결정: 캐시 전략' 항목에 의견 '{actor}: {marker}' 한 줄을 추가하세요. 다른 항목은 작업 대상이 아닙니다."
                elif actor == "A":
                    task = (f"'결정: 캐시 전략' 항목에 'A 결정: {a_decision}'를 기록하고, "
                            f"'담당: A' 항목을 '{marker}'로 갱신하세요.")
                elif actor == "B":
                    task = (f"판정자가 쓰는 준비 파일 {gate}가 생긴 뒤에 보드를 읽으세요. "
                            "준비 파일은 A 실행 종료만 알리며 결정 내용은 담지 않습니다. "
                            f"보드에서 A의 결정을 읽고 '담당: B' 항목에 '{marker}'와 읽은 결정 원문을 반영하세요. "
                            "보드에 결정이 없다면 추측하지 말고 해당 항목에 NOT_SEEN을 적고 보고하세요. 최대 90초까지 준비를 기다리세요.")
                else:
                    task = f"'담당: C' 항목을 '{marker}'로 갱신하세요."
                prompt = common + task
                (out / f"{actor}-prompt.txt").write_text(prompt)
                session_id = str(uuid.uuid4())
                cmd = argv_for(actor, workdirs[actor], [shared] if scenario in (3, 4) else [], prompt, session_id)
                meta = {"actor": actor, "harness": "claude" if actor in "AB" else "codex", "argv": cmd,
                        "cwd": str(workdirs[actor]), "stdin": "DEVNULL", "session_id_requested": session_id if actor in "AB" else None}
                write_json(out / f"{actor}-command.json", meta)
                launch_barrier.wait()
                start_ms = int(time.time() * 1000)
                captured = []
                proc = None
                try:
                    with (out / f"{actor}.jsonl").open("w") as log, (out / f"{actor}.stderr").open("w") as err:
                        proc = subprocess.Popen(cmd, cwd=workdirs[actor], env=env, stdin=subprocess.DEVNULL,
                                                stdout=subprocess.PIPE, stderr=err, text=True, bufsize=1,
                                                start_new_session=True)
                        timed_out = threading.Event()

                        def timeout():
                            if proc.poll() is None:
                                timed_out.set()
                                os.killpg(proc.pid, signal.SIGTERM)

                        timer = threading.Timer(180, timeout)
                        timer.start()
                        uses = {}
                        for line in proc.stdout:
                            log.write(line)
                            log.flush()
                            try:
                                e = json.loads(line)
                            except ValueError:
                                continue
                            captured.append(e)
                            if actor in "AB" and e.get("type") == "assistant":
                                for part in e.get("message", {}).get("content", []):
                                    if part.get("type") == "tool_use":
                                        uses[part["id"]] = part
                            if actor in "AB" and e.get("type") == "user":
                                content = e.get("message", {}).get("content", [])
                                if isinstance(content, list):
                                    for part in content:
                                        use = uses.get(part.get("tool_use_id"), {})
                                        if part.get("type") == "tool_result" and use.get("name") == "Read" and not part.get("is_error"):
                                            if "BOARD.md" in str(use.get("input", {})):
                                                read_seen.set()
                        code = proc.wait(timeout=10)
                        timer.cancel()
                        result = {"exit_code": code, "timed_out": timed_out.is_set()}
                except Exception as exc:
                    if proc and proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGTERM)
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
                    result = {"exception": type(exc).__name__, "detail": str(exc)}
                finally:
                    if actor == "A" and scenario in (3, 4):
                        write_json(gate, {"A_finished": True, "at": stamp()})
                if actor in "AB":
                    native = next((e.get("session_id") for e in captured if e.get("type") == "system" and e.get("subtype") == "init"), session_id)
                    metadata = json.dumps({"device_id": device_id, "account_uuid": account_uuid,
                                           "session_id": native}, separators=(",", ":"))
                    correlation = hashlib.sha256(metadata.encode()).hexdigest()[:32]
                    final = next((e for e in reversed(captured) if e.get("type") == "result"), {})
                    result["harness_success"] = bool(final) and not final.get("is_error") and result.get("exit_code") == 0
                    result["final_text"] = final.get("result")
                    result["response_model_labels"] = list(final.get("modelUsage", {}))
                else:
                    native = next((e.get("thread_id") for e in captured if e.get("type") == "thread.started"), None)
                    correlation = hashlib.sha256(native.encode()).hexdigest()[:32] if native else None
                    result["harness_success"] = any(e.get("type") == "turn.completed" for e in captured) and result.get("exit_code") == 0
                result.update(actor=actor, native_session_id=native, conversation_hash=correlation,
                              started_ms=start_ms, ended_ms=int(time.time() * 1000))
                if correlation:
                    try:
                        result["model_evidence"] = proxy_evidence(correlation)
                    except Exception as exc:
                        result["model_evidence"] = {"verified": False, "error": type(exc).__name__}
                else:
                    result["model_evidence"] = {"verified": False, "reason": "no native session"}
                write_json(out / f"{actor}-result.json", result)
                with state_lock:
                    actor_results[actor] = result

            watcher = threading.Thread(target=snapshot_loop, daemon=True)
            watcher.start()
            injector = threading.Thread(target=inject, daemon=True) if scenario == 2 else None
            if injector:
                injector.start()
            actors = [threading.Thread(target=actor_run, args=(actor,)) for actor in "ABC"]
            for thread in actors:
                thread.start()
            launch_barrier.wait()
            for thread in actors:
                thread.join()
            if injector:
                injector.join(timeout=85)
            stop_watch.set()
            watcher.join(timeout=2)
            write_json(out / "snapshots.json", snapshots)
            write_json(out / "injection.json", injected_record)
            finals = {}
            for actor, path in boards.items():
                text = path.read_text()
                (out / f"after-{actor}.md").write_text(text)
                finals[actor] = text
            summary = {"case": cid, "actors": actor_results, "injection": injected_record,
                       "marker_present_final": {a: expected[a] in finals[a] for a in "ABC"},
                       "progress_marker_present_final": {a: expected[a] + "-progress" in finals[a] for a in "ABC"} if scenario == 1 else None,
                       "A_decision_persisted": a_decision in finals["A"] if scenario in (3, 4) else None,
                       "B_reflected_A": a_decision in finals["B"] if scenario in (3, 4) else None,
                       "all_models_verified": len(actor_results) == 3 and all(x.get("model_evidence", {}).get("verified") for x in actor_results.values()),
                       "all_harnesses_success": len(actor_results) == 3 and all(x.get("harness_success") for x in actor_results.values()),
                       "ended_at": stamp()}
            write_json(out / "summary.json", summary)
            all_results.append({k: summary[k] for k in ("case", "marker_present_final", "B_reflected_A", "all_models_verified", "all_harnesses_success")})
            write_json(evidence / "progress.json", all_results)
            print(json.dumps(all_results[-1], ensure_ascii=False), flush=True)
            if not summary["all_models_verified"]:
                raise RuntimeError(f"model confirmation failed; no substitute permitted: {cid}")


if __name__ == "__main__":
    main()
