#!/usr/bin/env python3
"""Run the fast protocol gate in isolated homes, without models or credentials."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MODULES = ["tests.test_protocol", "tests.test_handoff", "tests.test_handoff_consumer",
           "tests.test_host_install",
           "tests.test_protocol_decisions",
           "tests.test_handoff_crash", "tests.test_handoff_pending_ids",
           "tests.test_mcp_dispatch", "tests.test_subagent_transport",
           "tests.test_mcp_identity", "tests.test_mcp_shared_process"]


def main():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="xsm-protocol-check-") as temp:
        env = {k: os.environ[k] for k in ("PATH", "LANG", "TMPDIR", "SYSTEMROOT") if k in os.environ}
        env.update(HOME=temp, XSM_HOME=temp + "/state", CODEX_HOME=temp + "/codex",
                   CLAUDE_CONFIG_DIR=temp + "/claude", PYTHONDONTWRITEBYTECODE="1",
                   PYTHON=sys.executable)
        commands = [[sys.executable, "-B", "-m", "unittest", *MODULES, "-q"],
                    [sys.executable, "-B", "-m", "unittest", "discover", "-s", "clients/tests",
                     "-p", "test_python*.py", "-q"],
                    ["node", "--test", "clients/tests/test_node_client.mjs",
                     "clients/tests/test_node_protocol.mjs", "clients/tests/test_node_host.mjs",
                     "clients/tests/test_node_host_binding.mjs", "clients/tests/test_opencode_binding.mjs"]]
        if not shutil.which("node", path=env.get("PATH")):
            print(json.dumps({"passed": False, "reason": "Node.js is required for client conformance"}))
            return 1
        try:
            for command in commands:
                remaining = 120 - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, 120)
                result = subprocess.run(command, cwd=ROOT, env=env, timeout=remaining)
                if result.returncode:
                    print(json.dumps({"passed": False, "command": command, "exit": result.returncode}))
                    return 1
            elapsed = time.monotonic() - started
            passed = result.returncode == 0 and elapsed <= 120
            print(json.dumps({"passed": passed, "seconds": round(elapsed, 3),
                              "python": sys.version.split()[0], "nodePython": env["PYTHON"],
                              "budgetSeconds": 120, "modules": MODULES}))
            return 0 if passed else 1
        except subprocess.TimeoutExpired:
            print(json.dumps({"passed": False, "reason": "120-second budget exceeded"}))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
