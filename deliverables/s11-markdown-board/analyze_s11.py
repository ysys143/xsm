#!/usr/bin/env python3
"""Read S11 evidence; never edit a board or launch a model."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re


def read_json(path):
    return json.loads(path.read_text())


def json_events(path):
    result = []
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result


def section(text, heading):
    match = re.search(r"(?m)^## " + re.escape(heading) + r"\s*$", text)
    if not match:
        return ""
    rest = text[match.end():]
    return re.split(r"(?m)^## ", rest, maxsplit=1)[0]


def is_board(path, cwd, expected):
    if not isinstance(path, str):
        return False
    value = Path(path)
    if not value.is_absolute():
        value = Path(cwd) / value
    return value.resolve() == Path(expected).resolve()


def shell_write(command):
    return bool(re.search(r"write_text|write_bytes|\btee\b|\bsed\s+-i|\bperl\s+-\S*i|"
                          r"\b(?:mv|cp)\s|\bcat\b[\s\S]*?>|open\([^)]*,\s*['\"](?:w|a)", command))


def operations(case, actor):
    meta = read_json(case / "case.json")
    board = meta["boards"][actor]
    cwd = meta["workdirs"][actor]
    evs = json_events(case / (actor + ".jsonl"))
    ops = []
    if actor in "AB":
        uses, results = {}, {}
        for index, e in enumerate(evs):
            content = e.get("message", {}).get("content", []) if isinstance(e.get("message"), dict) else []
            if not isinstance(content, list):
                continue
            for part in content:
                if e.get("type") == "assistant" and part.get("type") == "tool_use":
                    uses.setdefault(part["id"], (index, part))
                if part.get("type") == "tool_result":
                    results[part.get("tool_use_id")] = part
        for tool_id, (index, use) in uses.items():
            inp, name = use.get("input", {}), use.get("name")
            result = results.get(tool_id)
            status = "unknown" if result is None else "failed" if result.get("is_error") else "succeeded"
            if name in ("Read", "Edit", "Write") and is_board(inp.get("file_path"), cwd, board):
                method = {"Read": "read", "Edit": "item_edit", "Write": "whole_file_write"}[name]
                if name == "Edit" and inp.get("old_string", "").count("\n## ") >= 3:
                    method = "whole_file_edit"
                ops.append({"event_index": index, "id": tool_id, "tool": name,
                            "method": method, "status": status,
                            "failure_text": str(result.get("content", "")) if status == "failed" else None,
                            "new_text": inp.get("new_string", inp.get("content", ""))})
            elif name == "Bash":
                command = str(inp.get("command", ""))
                if "BOARD.md" in command:
                    ops.append({"event_index": index, "id": tool_id, "tool": name,
                                "method": "shell_write" if shell_write(command) else "read",
                                "status": status, "command": command,
                                "failure_text": str(result.get("content", "")) if status == "failed" else None})
            elif name in ("Agent", "Task"):
                ops.append({"event_index": index, "id": tool_id, "tool": name,
                            "method": "unexpected_subagent", "status": status})
    else:
        for index, e in enumerate(evs):
            if e.get("type") != "item.completed":
                continue
            item = e.get("item", {})
            if item.get("type") == "file_change":
                if any(is_board(c.get("path"), cwd, board) for c in item.get("changes", [])):
                    ops.append({"event_index": index, "id": item.get("id"), "tool": "file_change",
                                "method": "patch_update", "status": "succeeded" if item.get("status") == "completed" else "failed",
                                "scope_observation": "JSONL reports update/path, not the patch hunk coverage"})
            elif item.get("type") == "command_execution":
                command = item.get("command", "")
                if "BOARD.md" in command:
                    ops.append({"event_index": index, "id": item.get("id"), "tool": "command_execution",
                                "method": "shell_write" if shell_write(command) else "read",
                                "status": "succeeded" if item.get("exit_code") == 0 else "failed",
                                "command": command, "failure_text": item.get("aggregated_output") if item.get("exit_code") else None})
    return sorted(ops, key=lambda x: x["event_index"])


def marker_outcome(marker, final_text, observations, successful_tool_text=()):
    observed = any(marker in t for t in observations) or any(marker in t for t in successful_tool_text)
    return {"present_final": marker in final_text, "observed_written": observed,
            "lost_update": observed and marker not in final_text,
            "never_observed_and_missing": not observed and marker not in final_text}


def controls():
    assert marker_outcome("MARK", "MARK", ["MARK"])["lost_update"] is False
    assert marker_outcome("MARK", "gone", ["MARK"])["lost_update"] is True
    assert marker_outcome("MARK", "gone", ["nothing"])["never_observed_and_missing"] is True
    assert marker_outcome("MARK", "gone", ["nothing"])["lost_update"] is False
    text = "## 결정: 캐시 전략\nSECRET\n## 담당: B\nNOT_SEEN\n## 담당: C\nC\n"
    assert "SECRET" in text and "SECRET" not in section(text, "담당: B")
    assert shell_write("python3 -c \"Path('BOARD.md').write_text('x')\"")
    assert not shell_write("cat BOARD.md")
    return {"lost_update_mutation": "detected", "never_written_is_not_lost": "passed",
            "B_reflection_elsewhere_false_positive": "rejected", "shell_write_vs_read": "passed"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    cases = []
    methods, errors = Counter(), Counter()
    for case in sorted(args.evidence.glob("S11-*-r*")):
        if not (case / "summary.json").exists():
            continue
        meta, summary = read_json(case / "case.json"), read_json(case / "summary.json")
        scenario = meta["scenario"]
        snapshots = read_json(case / "snapshots.json")
        actor_ops = {a: operations(case, a) for a in "ABC"}
        outcomes = []
        failure_actions = []
        for actor in "ABC":
            final = (case / f"after-{actor}.md").read_text()
            path = Path(meta["boards"][actor]).resolve()
            observations = [(case / x["file"]).read_text() for x in snapshots if Path(x["path"]).resolve() == path]
            own = meta["markers"][actor]
            expected = [own, own + "-progress"] if scenario == 1 else [own]
            if scenario in (3, 4) and actor == "A":
                expected.append(meta["A_decision"])
            successes = [str(x.get("new_text", "")) for x in actor_ops[actor] if x["status"] == "succeeded" and x["method"] != "read"]
            for marker in expected:
                outcomes.append({"actor": actor, "marker": marker, **marker_outcome(marker, final, observations, successes)})
            for i, op in enumerate(actor_ops[actor]):
                if op["method"] == "read":
                    continue
                methods[(op["method"], op["status"])] += 1
                if op["status"] == "failed":
                    later = actor_ops[actor][i+1:]
                    retry = next((x for x in later if x["method"] != "read" and x["status"] == "succeeded"), None)
                    reread = bool(retry and any(x["method"] == "read" and x["status"] == "succeeded" and x["event_index"] < retry["event_index"] for x in later))
                    action = "no_successful_retry" if not retry else "reread_then_" + retry["method"] if reread else "retry_without_reread_" + retry["method"]
                    errors[action] += 1
                    failure_actions.append({"actor": actor, "failed_id": op["id"], "action": action,
                                            "failure_text": op.get("failure_text")})
        injection = read_json(case / "injection.json")
        if scenario == 2:
            injected = next((x for x in injection if x.get("status") == "injected"), None)
            if injected:
                final = (case / "after-A.md").read_text()
                observations = [(case / x["file"]).read_text() for x in snapshots]
                outcomes.append({"actor": "injector", "marker": injected["marker"],
                                 **marker_outcome(injected["marker"], final, observations + [(case / "injection-after.md").read_text()])})
        b_text = (case / "after-B.md").read_text()
        b_reflected = meta["A_decision"] in section(b_text, "담당: B") if scenario in (3, 4) else None
        result = {"case": case.name, "scenario": scenario, "all_models_verified": summary["all_models_verified"],
                  "all_harnesses_success": summary["all_harnesses_success"],
                  "lost_updates": sum(x["lost_update"] for x in outcomes),
                  "never_written_missing": sum(x["never_observed_and_missing"] for x in outcomes),
                  "marker_outcomes": outcomes, "operations": actor_ops, "failure_actions": failure_actions,
                  "A_decision_persisted": summary["A_decision_persisted"], "B_reflected_in_B_section": b_reflected,
                  "B_prompt_contains_A_oracle": meta["A_decision"] in (case / "B-prompt.txt").read_text() if scenario in (3, 4) else None,
                  "injection_status": [x.get("status") for x in injection],
                  "launch_spread_ms": max(x["started_ms"] for x in summary["actors"].values()) - min(x["started_ms"] for x in summary["actors"].values())}
        cases.append(result)
    aggregation = []
    for scenario in range(1, 5):
        chosen = [x for x in cases if x["scenario"] == scenario]
        aggregation.append({"scenario": f"S11-{scenario}", "completed": len(chosen),
                            "models_verified": sum(x["all_models_verified"] for x in chosen),
                            "harnesses_success": sum(x["all_harnesses_success"] for x in chosen),
                            "lost_updates": sum(x["lost_updates"] for x in chosen),
                            "never_written_missing": sum(x["never_written_missing"] for x in chosen),
                            "B_reflected": sum(x["B_reflected_in_B_section"] is True for x in chosen),
                            "injections": sum("injected" in x["injection_status"] for x in chosen)})
    writes = sum(n for (kind, status), n in methods.items() if status == "succeeded")
    whole_shell = sum(n for (kind, status), n in methods.items() if status == "succeeded" and kind in ("whole_file_write", "whole_file_edit", "shell_write"))
    result = {"analysis_controls": controls(), "completed_cases": len(cases), "launched_actors": len(cases)*3,
              "scenarios": aggregation,
              "write_methods": [{"method": kind, "status": status, "count": n} for (kind, status), n in sorted(methods.items())],
              "failure_actions": dict(errors), "successful_board_write_operations": writes,
              "whole_file_or_shell_successes": whole_shell,
              "whole_file_or_shell_fraction": whole_shell/writes if writes else None,
              "threshold_is_plan_proposal_not_user_policy": .1,
              "measurement_limitations": ["Snapshots poll every 5ms; transient writes shorter than that can be missed.",
                 "Codex file_change JSONL does not expose patch hunk coverage; patch-update counts are tool-level.",
                 "Runner provisional B_reflected_A checks the whole board; this analysis deliberately checks the B section only.",
                 "No failed board-write event means no observation of failure recovery; it is not proof that stale edits are always rejected."],
              "cases": cases}
    target = args.output or args.evidence / "analysis.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("completed_cases", "scenarios", "write_methods", "failure_actions", "whole_file_or_shell_fraction")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
