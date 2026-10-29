#!/usr/bin/env python3
"""Reason 조사 문서의 추적·원본·실행 근거를 재검사한다. 제품 수용 시험과 구분한다."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlparse


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PIN = "b3557ff454cd26a04c2a18804ba83ae5db8b119d"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(coverage, documents, source_roots, native_root):
    errors = []
    checks = {}
    require = lambda condition, error: errors.append(error) if not condition else None
    rows = coverage["requirements"]
    require([r["id"] for r in rows] == [f"R{i:02}" for i in range(1, 44)], "requirement set")
    adrs = {f.name[:4]: f for f in documents if f.parent == REPO / "docs/adr" and f.name[:4].isdigit()}
    require(set(adrs) == {str(n).zfill(4) for n in range(15, 24)}, "ADR set")
    acceptance = {}
    for n, file in adrs.items():
        text = documents[file]
        require("- 상태: Proposed" in text and "- 상태: Accepted" not in text, f"ADR status:{n}")
        for heading in ["질문", "맥락", "선택지", "제안 계약", "수용 검사", "비용과 되돌리기", "미결 매개변수", "결정"]:
            require(f"## {heading}" in text, f"ADR section:{n}:{heading}")
        for a in re.findall(r"^- (A\d{2}-\d{2}):", text, re.M):
            require(a not in acceptance, f"duplicate acceptance:{a}")
            acceptance[a] = n
    require(len(acceptance) == 62, "acceptance count")
    for row in rows:
        for n in row["adrs"]:
            require(n in adrs, f"missing ADR:{row['id']}:{n}")
            if n in adrs:
                require(row["id"] in documents[adrs[n]], f"missing ADR backlink:{row['id']}:{n}")
        for a in row["acceptance"]:
            require(acceptance.get(a) in row["adrs"], f"acceptance outside ADR:{row['id']}:{a}")
        for file in row["xsm"] + row["supporting_artifacts"]:
            require((REPO / file).is_file(), f"artifact missing:{file}")
        require(bool(row["evidence"]), f"no evidence:{row['id']}")
        for evidence in row["evidence"]:
            if evidence["kind"] == "source":
                require((source_roots["current"] / evidence["path"]).is_file(), f"source missing:{row['id']}:{evidence['path']}")
        require(bool(row["observed"]) and bool(row["xsm_assessment"]), f"empty finding:{row['id']}")
    links = pinned = 0
    for file, text in documents.items():
        require(not re.search(r"[\u3400-\u9fff]", text), f"unexpected CJK prose:{file.name}")
        # 코드 블록의 예시 링크는 제외한다.
        prose = re.sub(r"```.*?```", "", text, flags=re.S)
        for dest in re.findall(r"\[[^\]]+\]\(([^)]+)\)", prose):
            dest = dest.strip("<>")
            if dest.startswith(("http://", "https://")):
                m = re.search(r"github.com/reason-machines/reason-network/(?:blob|tree)/([a-f0-9]{40})/([^#]+)", dest)
                if m:
                    pinned += 1
                    base = source_roots["current"] if m[1] == PIN else source_roots["baseline"]
                    require((base / unquote(m[2])).exists(), f"pinned source target:{dest}")
            elif not dest.startswith("#"):
                target = unquote(dest.split("#", 1)[0])
                require((file.parent / target).exists(), f"broken link:{file.name}:{dest}")
            links += 1
    manifest = json.loads((HERE / "source-manifest.json").read_text())
    source_files = 0
    for snapshot in manifest["snapshots"]:
        base = source_roots[snapshot["label"]]
        for item in snapshot["files"]:
            target = base / item["path"]
            require(target.exists() and sha(target) == item["sha256"], f"snapshot changed:{snapshot['label']}:{item['path']}")
            source_files += 1
    native = json.loads((HERE / "full-native-analysis.json").read_text())
    for kind, item in zip(["cli", "engine"], native["programs"]):
        base = native_root / "evidence" / f"full-{kind}"
        require(not item["analysis_timed_out"] and not item["analysis_timeout_argument_present"] and item["exit"] == 0, f"native incomplete:{kind}")
        require(all(item[k] for k in ["analysis_success_line", "post_analysis_success_line", "save_success_line"]), f"native execution:{kind}")
        for name, key in [("functions.jsonl", "inventory_sha256"), ("summary.json", "summary_sha256")]:
            require(sha(base / name) == item[key], f"native output changed:{kind}:{name}")
        log_path = native_root / 'evidence' / f'full-{kind}.stdout'
        require(sha(log_path) == item['stdout_sha256'], f"native log changed:{kind}")
        log = log_path.read_text()
        require(all(s in log for s in ['Analysis succeeded for file', 'Post-analysis succeeded for file', 'Save succeeded for processed file']), f"native success log:{kind}")
        count = sum(1 for _ in (base / "functions.jsonl").open())
        require(count == item["inventory_rows"] == item["inventory_verified_rows"], f"native row count:{kind}")
        target = native_root / 'targets' / item['program']
        installed = Path.home() / ('Library/Application Support/Reason/CLI/versions/0.2.557/reason' if kind == 'cli' else '.reason/bin/reason-network')
        require(sha(target) == item['source_sha256'] == sha(installed), f"native target changed:{kind}")
        require(sha(HERE/'FullNativeInventory.java') == item['exporter_sha256'], f"native exporter changed:{kind}")
    cli = (Path.home()/'Library/Application Support/Reason/CLI/versions/0.2.557/reason').read_bytes()
    modules = json.loads((HERE/'cli-extraction.json').read_text())
    modules = modules if isinstance(modules,list) else modules['modules']
    extra = json.loads((HERE/'cli-additional-extraction.json').read_text())
    for item in modules + extra:
        offset = item.get('offset',item.get('file_offset',item.get('start')))
        end = item.get('end',offset+item['bytes'])
        require(hashlib.sha256(cli[offset:end]).hexdigest() == item['sha256'], f"CLI module changed:{offset}")
    for n in ["ipc-probes", "mcp-probes", "worker-probes", "auth-probes", "notify-probes", "notify-baseline-probes"]:
        p = json.loads((HERE / f"{n}.json").read_text())
        require(p["passed"] and all(x["passed"] for x in p["results"]), f"probe observation:{n}")
        if 'processes_stopped' in p:
            require(p['processes_stopped'], f"probe still running:{n}")
        if 'process_stopped' in p:
            require(p['process_stopped'], f"probe still running:{n}")
    e2e = json.loads((HERE / "e2e-results.json").read_text())
    require(e2e["runnable_suites"] == 7 and e2e["latest_counts"] == {"passed": 309, "failed": 1}, "E2E failures preserved")
    for item in e2e["runs"]:
        for suffix in ["stdout", "stderr"]:
            require(sha(native_root / "e2e" / f"{item['label']}.{suffix}") == item[f"{suffix}_sha256"], f"E2E log changed:{item['label']}:{suffix}")
    tracked = subprocess.check_output(["git", "ls-files", "xsm"], cwd=REPO, text=True).splitlines()
    changed = []
    for name in tracked:
        if name.endswith(".py"):
            before = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=REPO)
            if before != (REPO / name).read_bytes():
                changed.append(name)
    adr_changes = subprocess.check_output(["git", "diff", "HEAD", "--name-only", "--", "docs/adr"], cwd=REPO, text=True).splitlines()
    old_adrs = [p for p in adr_changes if Path(p).name[:4].isdigit() and int(Path(p).name[:4]) <= 14]
    require(not changed, f"product changed:{changed}")
    require(not old_adrs, f"existing ADR changed:{old_adrs}")
    parse_files = []
    for file in HERE.iterdir():
        if file.suffix == ".json":
            json.loads(file.read_text());parse_files.append(file.name)
        if file.suffix == ".py":
            ast.parse(file.read_text());parse_files.append(file.name)
    # 실제 초대·비밀키 패턴. 설명용 rn1- 또는 짧은 시험 식별자는 허용한다.
    scan = list(documents) + list(HERE.glob("*.json")) + list(HERE.glob("*.py")) + list(HERE.glob("*.mjs"))
    for f in scan:
        text = f.read_text()
        require(not re.search(r"rn1-[A-Za-z0-9_-]{80,}", text), f"invite leaked:{f.name}")
        require(not re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text), f"private key leaked:{f.name}")
    checks.update(adr_count=len(adrs), requirement_count=len(rows), acceptance_count=len(acceptance), markdown_links_checked=links, pinned_source_links_checked=pinned, source_snapshot_files_checked=source_files, xsm_python_files_checked=sum(x.endswith('.py') for x in tracked), xsm_python_changed=changed, existing_adr_bodies_changed=old_adrs, parsed_files=len(parse_files), native_programs=len(native['programs']), native_full_auto_analysis='completed without per-file timeout', native_target_binaries_unchanged=True, cli_modules_checked=len(modules)+len(extra), probe_cases={n:len(json.loads((HERE/f'{n}.json').read_text())['results']) for n in ['ipc-probes','mcp-probes','worker-probes','auth-probes','notify-probes','notify-baseline-probes']}, e2e_latest=e2e['latest_counts'],credential_scan_files=len(scan))
    return checks, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-source", type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path, required=True)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = {p:p.read_text() for p in list(HERE.glob("*.md")) + [HERE.parent/'reason-network.md', HERE.parent/'README.md', REPO/'docs/adr/README.md'] + [p for p in (REPO/'docs/adr').glob('*.md') if p.name[:4].isdigit() and 15<=int(p.name[:4])<=23]}
    coverage = json.loads((HERE/'coverage.json').read_text())
    roots = dict(current=args.current_source, baseline=args.baseline_source)
    checks, errors = validate(coverage, documents, roots, args.native_root)
    # 검사가 실제 결함을 거부하는지 원본을 수정하지 않는 변이 입력으로 확인한다.
    mutated=json.loads(json.dumps(coverage));mutated['requirements'].pop()
    _, bad=validate(mutated, documents, roots, args.native_root)
    missing='requirement set' in bad
    doc_mut=dict(documents);adr=next(p for p in documents if p.name.startswith('0015-'))
    doc_mut[adr]=doc_mut[adr].replace('- 상태: Proposed','- 상태: Accepted')+'\n[broken](missing-research-target.md)\n'
    _, bad=validate(coverage, doc_mut, roots, args.native_root)
    negatives=dict(missing_requirement_detected=missing, accepted_status_detected=any(x.startswith('ADR status:') for x in bad), broken_link_detected=any(x.startswith('broken link:') for x in bad))
    if not all(negatives.values()):errors.append('negative control failed')
    checks['negative_controls']=negatives
    result=dict(date='2026-10-24',status='passed' if not errors else 'failed',checks=checks,errors=errors,scope='문서·출처·원본·실행 기록의 수집 검증. 제품 수용 검사 62개를 실행했다는 뜻이 아니다.',review_method='코디네이터 자체 대조. 이번 후속 실행에서 독립 리뷰어를 새로 실행하지 않음.',limits=[])
    result['limits']=['E2E 알림 로그 검사 1건 실패 유지','실제 물리 원격·OS UI 경쟁·실제 하네스 공유 MCP 배치 미검증','CLI 모듈의 자식 모델·HTTP·전송 일부는 가짜이며 전체 제품 의미 동등성 미검증','원본 사용자 홈 전체의 바이트 불변은 검사하지 않음']
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
