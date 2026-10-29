#!/usr/bin/env python3
"""고정 소스의 E2E를 합성 하네스 환경에서 실행하고 원시 로그를 사설 경로에 보관한다."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--old-engine", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite", choices=["hooks", "codex_busy", "two_machines", "names", "mixed_versions", "regional_relays", "guided"], required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("CLAUDE", "CODEX", "REASON", "TINCAN", "GROK", "GEMINI", "CURSOR", "OPENCODE", "COPILOT")) or key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(key, None)
    env.update(REASON_NETWORK_NO_UPDATE="1", REASON_NETWORK_NO_TRAY="1", REASON_NETWORK_NO_SERVICE="1", PYTHONDONTWRITEBYTECODE="1", REASON_NETWORK_OLD_BIN=str(args.old_engine.resolve()))
    script = args.source.resolve() / "tests" / "e2e" / f"{args.suite}.py"
    if not args.old_engine.is_file():
        raise FileNotFoundError(args.old_engine)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()
    with (args.output_dir / f"{args.label}.stdout").open("w") as out, (args.output_dir / f"{args.label}.stderr").open("w") as err:
        process = subprocess.Popen(["python3", str(script)], cwd=args.source, env=env, stdout=out, stderr=err)
        (args.output_dir / f"{args.label}-start.json").write_text(json.dumps(dict(pid=process.pid, started=start, suite=args.suite, old_engine=str(args.old_engine.resolve()))))
        exit_code = process.wait()
    lines = (args.output_dir / f"{args.label}.stdout").read_text().splitlines()
    result = dict(suite=args.suite, label=args.label, exit=exit_code, elapsed=time.time() - start, passed_lines=sum(x.startswith("PASS:") for x in lines), failed_lines=sum(x.startswith("FAIL:") for x in lines), script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(), physical_hosts=1, native_llm_calls=0)
    (args.output_dir / f"{args.label}-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
