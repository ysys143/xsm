#!/usr/bin/env python3
"""Read-only S11b measurements; no model, registration, render, or settings writes."""
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from xsm import doc
EXPECTED = {"## 결정: 캐시 전략", "## 담당: A", "## 담당: B", "## 담당: C", "## 진행 기록"}


def jread(path):
    return json.loads(path.read_text())


def events(path):
    result = []
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result


def has_marker(marker, text):
    # A marker's '-progress' extension is another requested contribution.
    return bool(re.search(r'(?<![A-Za-z0-9_-])' + re.escape(marker) + r'(?![A-Za-z0-9_-])', text))


def marker_state(marker, bodies, agent_render, final_render, observed_bodies):
    observed = any(has_marker(marker, x) for x in observed_bodies)
    return {'marker': marker, 'in_final_nodes': has_marker(marker, bodies),
            'in_agent_final_render': has_marker(marker, agent_render),
            'in_judge_final_render': has_marker(marker, final_render),
            'observed_in_node_snapshot': observed,
            'canonical_node_marker_lost': observed and not has_marker(marker, bodies)}


def parse_nodes(files):
    nodes, bad = {}, []
    for filename, text in files.items():
        try:
            node = doc._parse(text)
            if node.get("id") + ".md" != filename:
                raise ValueError("filename/id mismatch")
            nodes[node["id"]] = node
        except Exception as exc:
            bad.append({"filename": filename, "error": type(exc).__name__})
    broken = [{"node": key, "parent": p} for key, node in nodes.items() for p in node["parents"] if p not in nodes]
    return nodes, bad, broken


def shell_tokens(command):
    try:
        outer = shlex.split(command)
        if len(outer) >= 3 and Path(outer[0]).name in ("zsh", "bash", "sh") and "c" in outer[1]:
            command = outer[2]
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return []


def doc_actions(command):
    tokens = shell_tokens(command)
    result = []
    for i in range(len(tokens) - 2):
        if Path(tokens[i]).name == "xsm" and tokens[i+1] == "doc":
            action = tokens[i+2]
            if action in ("add", "render", "log", "show", "next", "leaves"):
                end = next((k for k in range(i+3, len(tokens)) if tokens[k] in ("&&", ";", "||", "|")), len(tokens))
                if "--help" not in tokens[i+3:end]:
                    result.append(action)
    return result


def calls(case, actor):
    evs = events(case / f"{actor}.jsonl")
    result = []
    if actor in "AB":
        uses, results = {}, {}
        for i, e in enumerate(evs):
            content = e.get("message", {}).get("content", []) if isinstance(e.get("message"), dict) else []
            if not isinstance(content, list):
                continue
            for part in content:
                if e.get("type") == "assistant" and part.get("type") == "tool_use":
                    uses.setdefault(part["id"], (i, part))
                if part.get("type") == "tool_result":
                    results[part.get("tool_use_id")] = part
        for tid, (i, use) in uses.items():
            answer = results.get(tid)
            result.append({"id": tid, "index": i, "tool": use["name"], "args": use.get("input", {}),
                           "status": "unknown" if answer is None else "failed" if answer.get("is_error") else "succeeded",
                           "output": str(answer.get("content", "")) if answer else ""})
    else:
        for i, e in enumerate(evs):
            if e.get("type") != "item.completed":
                continue
            item = e.get("item", {})
            if item.get("type") == "command_execution":
                result.append({"id": item["id"], "index": i, "tool": "Bash",
                               "args": {"command": item.get("command", "")},
                               "status": "succeeded" if item.get("exit_code") == 0 else "failed",
                               "output": item.get("aggregated_output", "")})
            elif item.get("type") == "file_change":
                result.append({"id": item["id"], "index": i, "tool": "patch",
                               "args": {"changes": item.get("changes", [])},
                               "status": "succeeded" if item.get("status") == "completed" else "failed", "output": ""})
            elif item.get("type") == "mcp_tool_call":
                result.append({"id": item["id"], "index": i, "tool": item.get("tool", ""),
                               "args": item.get("arguments", {}),
                               "status": "succeeded" if item.get("status") == "completed" else "failed",
                               "output": json.dumps(item.get("result", ""), ensure_ascii=False)})
    return result


def classify(call):
    tool, args = call["tool"], call["args"]
    encoded = json.dumps(args, ensure_ascii=False)
    actions = doc_actions(args.get("command", "")) if tool == "Bash" else []
    if "doc_add" in tool:
        actions.append("add")
    for name in ("render", "next", "show", "log", "leaves"):
        if "doc_" + name in tool:
            actions.append(name)
    added = sorted(set(re.findall(r"added node ([0-9a-f]{12})", call["output"]))) if "add" in actions else []
    methods = []
    if added:
        methods += ["doc_add"] * len(added)
    if "add" in actions and call["status"] == "failed":
        methods.append("doc_add_failed_tool_call")
    if "render" in actions:
        rendered = re.findall(r'rendered [^\n]+ from \d+ node\(s\)', call['output'])
        if rendered:
            methods += ['doc_render'] * len(rendered)
        elif call['status'] == 'succeeded' and 'doc_render' in tool:
            methods.append('doc_render')
        else:
            methods.append('doc_render_not_confirmed')
    for action in ("next", "show", "log", "leaves"):
        if action in actions:
            methods.append("read_doc_" + action)
    if not actions:
        if tool == "Read" and "BOARD.md" in encoded:
            methods.append("read_node_file" if ".nodes" in encoded else "read_render_file")
        elif tool in ("Edit", "Write", "patch") and "BOARD.md" in encoded:
            methods.append("direct_node_file_" + tool if ".nodes" in encoded else "direct_render_file_" + tool)
        elif tool == "Bash" and "BOARD.md" in encoded:
            command = args.get("command", "")
            writes = bool(re.search(r"write_text|write_bytes|\btee\b|\bsed\s+-i|\bcat\b[\s\S]*?>|open\([^)]*,\s*['\"](?:w|a)", command))
            methods.append(("direct_node_file_shell" if ".nodes" in command else "direct_render_file_shell") if writes
                           else "read_node_file" if ".nodes" in command else "read_render_file")
    return methods, added, actions


def controls():
    sample = {"tool": "Bash", "args": {"command": "xsm doc add BOARD.md --tag result --text 'MARK' && xsm doc render BOARD.md"},
              "status": "succeeded", "output": "added node 0123456789ab [result] to BOARD.md.nodes\nrendered BOARD.md from 1 node(s)"}
    assert classify(sample)[0] == ["doc_add", "doc_render"]
    assert not doc_actions("xsm doc add --help")
    fake = dict(sample, args={"command": "cat BOARD.md"}, output="added node 0123456789ab")
    assert "doc_add" not in classify(fake)[0]
    failed_chain = dict(sample, status='failed', output='added node 0123456789ab [result] to BOARD.md.nodes\nrefused: later command failed')
    assert 'doc_add' in classify(failed_chain)[0] and 'doc_render' not in classify(failed_chain)[0]
    assert 'doc_render_not_confirmed' in classify(failed_chain)[0]
    malformed = {"0123456789ab.md": "---\nid: 0123456789ab\nparents: missing\ntags: result\n---\n\nMARK\n"}
    assert parse_nodes(malformed)[2]
    assert 'MARK' not in 'render without marker' and 'MARK' in parse_nodes(malformed)[0]['0123456789ab']['body']
    assert not has_marker('TOKEN-A', 'TOKEN-A-progress')
    assert has_marker('TOKEN-A', '## 담당: A\nTOKEN-A\n')
    assert marker_state('TOKEN-A', '', '', '', ['TOKEN-A'])['canonical_node_marker_lost']
    assert not marker_state('TOKEN-A', '', '', '', [])['canonical_node_marker_lost']
    retained = marker_state('TOKEN-A', 'TOKEN-A', '', '', ['TOKEN-A'])
    assert retained['in_final_nodes'] and not retained['in_judge_final_render'] and not retained['canonical_node_marker_lost']
    return {"doc_add_vs_render": "passed", "help_not_add": "passed", "echoed_add_not_counted": "rejected",
            "missing_parent_negative_control": "detected", "node_preservation_not_render_presence": "distinguished",
            "own_marker_not_inferred_from_progress_prefix": "rejected",
            "short_circuited_render_not_called_success": "rejected",
            "delete_observed_node_marker_mutation": "detected",
            "never_written_not_node_loss": "passed"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    cases, by_harness = [], defaultdict(Counter)
    for case in sorted(args.evidence.glob("S11b-*-r*")):
        if not (case / "summary.json").exists():
            continue
        meta, summary = jread(case / "case.json"), jread(case / "summary.json")
        files = jread(case / "final-nodes.json")
        initial = jread(case / "initial-nodes.json")
        nodes, malformed, broken = parse_nodes(files)
        bodies = "\n".join(x["body"] for x in nodes.values())
        agent_render = (case / "agent-final-rendered.md").read_text()
        final_render = (case / "judge-final-rendered.md").read_text()
        observed_node_bodies = []
        for snapshot in jread(case / "snapshots.json"):
            if '.nodes/' in snapshot['path']:
                try:
                    observed_node_bodies.append(doc._parse((case / snapshot['file']).read_text())['body'])
                except Exception:
                    pass
        lost, renderer_missing, marker_rows, added_rows, usage = [], [], [], [], {}
        for actor in "ABC":
            expected = [meta["markers"][actor]]
            if meta["scenario"] == "1":
                expected.append(meta["markers"][actor] + "-progress")
            if meta["scenario"] == "4" and actor == "A":
                expected.append(meta["A_value"])
            for marker in expected:
                row = {"actor": actor, **marker_state(marker, bodies, agent_render, final_render, observed_node_bodies)}
                marker_rows.append(row)
                if not row['in_final_nodes'] and not row['in_judge_final_render']:
                    lost.append(row)
                if row['in_final_nodes'] and not row['in_judge_final_render']:
                    renderer_missing.append(row)
            rows = calls(case, actor)
            usage[actor] = []
            for call in rows:
                methods, ids, actions = classify(call)
                for method in methods:
                    status = 'succeeded' if method in ('doc_add','doc_render') else 'not_confirmed' if method == 'doc_render_not_confirmed' else call['status']
                    by_harness["claude" if actor in "AB" else "codex"][(method, status)] += 1
                if methods:
                    usage[actor].append({"id": call["id"], "tool": call["tool"], "status": call["status"],
                                         "methods": methods, "actions": actions, "args": call["args"],
                                         "output": call["output"] if call["status"] == "failed" else None})
                for nid in ids:
                    node = nodes.get(nid)
                    added_rows.append({"actor": actor, "node_id": nid, "present_final": node is not None,
                                       "parents": node.get("parents") if node else None,
                                       "tags": node.get("tags") if node else None,
                                       "body": node.get("body") if node else None,
                                       "parent_items": [k for k, v in meta["initial"]["items"].items() if node and v in node["parents"]]})
        injected = jread(case / "injection.json")
        injection_marker = meta.get("injection_marker")
        if injection_marker and any(x.get("status") == "injected" for x in injected):
            marker_rows.append({"actor": "injector", **marker_state(injection_marker, bodies, agent_render, final_render, observed_node_bodies)})
        b_contributions = [x for x in added_rows if x["actor"] == "B" and x.get("body") and has_marker(meta["markers"]["B"], x["body"])]
        result = {"case": case.name, "scenario": meta["scenario"], "node_count": len(nodes),
                  "rendered_bytes": len(final_render.encode()), "agent_rendered_bytes": len(agent_render.encode()),
                  "all_models_verified": summary["all_models_verified"], "all_harnesses_success": summary["all_harnesses_success"],
                  "protected_files_unchanged": all(x["unchanged"] for x in summary["protected_checks"]),
                  "missing_contributions_nodes_or_render": lost, "nodes_preserved_but_not_rendered": renderer_missing,
                  "marker_rows": marker_rows, "malformed_node_files": malformed, "missing_parents": broken,
                  "initial_node_changed_or_removed": [k for k, v in initial.items() if files.get(k) != v],
                  "agent_render_missing_headings": sorted(EXPECTED - set(re.findall(r'^## .+$', agent_render, re.M))),
                  "judge_render_missing_headings": sorted(EXPECTED - set(re.findall(r'^## .+$', final_render, re.M))),
                  "injection": injected, "render_only_injection_absent_after_judge_render": meta['scenario'] == '2-render' and bool(injection_marker) and injection_marker not in final_render,
                  "node_injection_preserved": meta['scenario'] == '2-node' and bool(injection_marker) and injection_marker in bodies,
                  "B_reflected_A_in_own_node": any(meta['A_value'] in x['body'] for x in b_contributions) if meta['scenario'] == '4' else None,
                  "added_nodes": added_rows, "usage": usage}
        cases.append(result)
    aggregate = []
    for scenario in ("1", "2-render", "2-node", "4"):
        rows = [x for x in cases if x["scenario"] == scenario]
        aggregate.append({"scenario": scenario, "completed": len(rows),
                          "missing_agent_contributions": sum(len(x['missing_contributions_nodes_or_render']) for x in rows),
                          "canonical_node_markers_lost": sum(z['canonical_node_marker_lost'] for x in rows for z in x['marker_rows']),
                          "nodes_preserved_but_not_rendered": sum(len(x['nodes_preserved_but_not_rendered']) for x in rows),
                          "render_only_injection_disappeared": sum(x['render_only_injection_absent_after_judge_render'] for x in rows),
                          "node_injection_preserved": sum(x['node_injection_preserved'] for x in rows),
                          "agent_structure_damage_cases": sum(bool(x['agent_render_missing_headings']) for x in rows),
                          "judge_structure_damage_cases": sum(bool(x['judge_render_missing_headings']) for x in rows),
                          "broken_parent_edges": sum(len(x['missing_parents']) for x in rows),
                          "B_reflected": sum(x['B_reflected_A_in_own_node'] is True for x in rows),
                          "node_counts": [x['node_count'] for x in rows],
                          "rendered_bytes": [x['rendered_bytes'] for x in rows]})
    result = {"completed_cases": len(cases), "native_actor_runs": len(cases)*3,
              "controls": controls(), "scenarios": aggregate,
              "by_harness": {h: [{"method": m, "status": s, "count": n} for (m, s), n in sorted(c.items())] for h, c in by_harness.items()},
              "measurement_notes": ["doc_add counts successful returned node IDs, not Bash invocations; failed tool calls counted separately.",
                 "Official render writes are separated from direct edits of the rendered file.",
                 "Agent-final projection and the explicit judge's final render are separate artifacts.",
                 "Absent from render but present in nodes is not counted as canonical contribution loss.",
                 "Compound-shell direct file writes mixed with official doc commands require manual review."],
              "cases": cases}
    (args.output or args.evidence/'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('completed_cases','scenarios','by_harness')},ensure_ascii=False))


if __name__ == "__main__":
    main()
