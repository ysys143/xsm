#!/usr/bin/env python3
"""Run the fast protocol gate in isolated homes, without models or credentials."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import signal
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MODULES = ["tests.test_owned_probe_observer", "tests.test_cli_worker_approval", "tests.test_process_start", "tests.test_question_service", "tests.test_send_service", "tests.test_materials", "tests.test_multisend", "tests.test_question_groups", "tests.test_board_service", "tests.test_board", "tests.test_team_service", "tests.test_teams", "tests.test_native_probe_platform", "tests.test_protocol_conformance", "tests.test_protocol", "tests.test_handoff", "tests.test_handoff_consumer",
           "tests.test_scope_service",
           "tests.test_native_worker_probe",
           "tests.test_doc_service", "tests.test_doc",
           "tests.test_file_uploads",
           "tests.test_file_contract",
           "tests.test_protocol_gate",
           "tests.test_subscription_probe",
           "tests.test_protocol_directory",
           "tests.test_handover_service", "tests.test_handover",
           "tests.test_owned_interfaces", "tests.test_owned_workers", "tests.test_owned_native", "tests.test_owned_requests", "tests.test_owned_review_fixes",
           "tests.test_handoff_read_cache",
           "tests.test_hermes_binding",
           "tests.test_hermes_worker_cli",
           "tests.test_openclaw_schema",
           "tests.test_host_install",
           "tests.test_host_ui_config", "tests.test_component_leases",
           "tests.test_install_lock_alias",
           "tests.test_protocol_decisions",
           "tests.test_handoff_crash", "tests.test_handoff_pending_ids",
           "tests.test_mcp_dispatch", "tests.test_subagent_transport",
           "tests.test_mcp_identity", "tests.test_mcp_shared_process"]
CONFORMANCE_MODULES = ["tests.test_protocol_conformance"]
NATIVE_MODULES = ["tests.test_native_worker_catalog", "tests.test_native_worker_control",
                  "tests.test_native_worker_provider", "tests.test_native_worker_retention",
                  "tests.test_native_worker_lineage", "tests.test_opencode_worker_cli", "tests.test_pi_worker_cli",
                  "tests.test_owned_cancellation"]
NATIVE_MODULES += ["tests.test_hermes_cancel_observer"]
NATIVE_MODULES += ["tests.test_openclaw_worker_session", "tests.test_openclaw_worker_frontend", "tests.test_openclaw_worker_transport", "tests.test_openclaw_worker_provider", "tests.test_openclaw_worker_cancellation"]


def run_phase(commands, env, root, deadline, offset):
    """Independent Python groups overlap waits; each has its own state and profiles."""
    jobs = []
    try:
        for index, command in enumerate(commands, offset):
            folder = Path(root) / ('group-%d' % index)
            folder.mkdir()
            group_env = dict(env, HOME=str(folder / 'home'), XSM_HOME=str(folder / 'state'),
                             CODEX_HOME=str(folder / 'codex'), CLAUDE_CONFIG_DIR=str(folder / 'claude'))
            Path(group_env['HOME']).mkdir()
            stream = (folder / 'output.log').open('w+')
            try:
                process = subprocess.Popen(command, cwd=ROOT, env=group_env, stdout=stream,
                                           stderr=subprocess.STDOUT, start_new_session=True)
            except BaseException:
                stream.close()
                raise
            jobs.append((process, stream, command))
        while any(process.poll() is None for process, _, _ in jobs):
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(commands, 120)
            if any(process.poll() not in (None, 0) for process, _, _ in jobs):
                return next(command for process, _, command in jobs if process.poll() not in (None, 0))
            time.sleep(.02)
        return next((command for process, _, command in jobs if process.returncode), None)
    finally:
        # Also reap descendants if a test failed or the shared deadline expired.
        for process, _, _ in jobs:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
        for _, stream, _ in jobs:
            stream.seek(0)
            shutil.copyfileobj(stream, sys.stdout)
            stream.close()
        sys.stdout.flush()


def main(*, validator_path=None):
    started = time.monotonic()
    if validator_path is None:
        # Resolve only the installed development library before HOME isolation;
        # never copy credentials or the parent's full Python/environment paths.
        spec = importlib.util.find_spec('jsonschema')
        if spec is not None and spec.origin:
            validator_path = Path(spec.origin).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="xsm-protocol-check-") as temp:
        env = {k: os.environ[k] for k in ("PATH", "LANG", "TMPDIR", "SYSTEMROOT") if k in os.environ}
        env.update(HOME=temp, XSM_HOME=temp + "/state", CODEX_HOME=temp + "/codex",
                   CLAUDE_CONFIG_DIR=temp + "/claude", PYTHONDONTWRITEBYTECODE="1",
                   PYTHON=sys.executable)
        core_modules = [module for module in MODULES if module not in CONFORMANCE_MODULES]
        def validation_command(script, output):
            if validator_path is None:
                return [sys.executable, "-B", script, "--output", output]
            # Trusted development-only dependency root, scoped to these two
            # commands. Do not forward ambient PYTHONPATH to protocol children.
            bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
            return [sys.executable, "-B", "-c", bootstrap, str(validator_path), script, "--output", output]
        commands = [[sys.executable, "-B", "-m", "unittest", *core_modules, "-q"],
                    [sys.executable, "-B", "-m", "unittest", "discover", "-s", "clients/tests",
                     "-p", "test_python*.py", "-q"],
                    [sys.executable, "-B", "examples/independent-participant/local_v3_fixtures.py",
                     "--bundle", "docs/protocol", "--output", temp + "/independent-local.json"],
                    [sys.executable, "-B", "-m", "unittest", *NATIVE_MODULES, "-q"],
                    [sys.executable, "-B", "examples/independent-participant/local_v5_fixtures.py",
                     "--output", temp + "/independent-v5-local.json"],
                    [sys.executable, "-B", "examples/independent-participant/local_v6_fixtures.py",
                     "--bundle", "docs/protocol", "--output", temp + "/independent-v6-local.json"],
                    validation_command("scripts/check-protocol-schema.py", temp + "/schema.json"),
                    validation_command("scripts/check-independent-v7.py", temp + "/independent-v7-local.json"),
                    ["node", "--test", "clients/tests/test_node_client.mjs",
                     "clients/tests/test_json_wire.mjs", "clients/tests/test_native_worker_control.mjs",
                     "clients/tests/test_node_protocol.mjs", "clients/tests/test_node_host.mjs",
                     "clients/tests/test_node_host_binding.mjs", "clients/tests/test_opencode_binding.mjs", "clients/tests/test_pi_binding.mjs",
                     "clients/tests/test_opencode_question_ui.mjs", "clients/tests/test_opencode_ui_channel.mjs",
                     "clients/tests/test_openclaw_binding.mjs", "clients/tests/test_openclaw_context_queue.mjs"]]
        if not shutil.which("node", path=env.get("PATH")):
            print(json.dumps({"passed": False, "reason": "Node.js is required for client conformance"}))
            return 1
        try:
            # Black-box subprocess checks have no shared test state with the other groups.
            # Keep the full module inventory while overlapping their process/I/O waits.
            external = [sys.executable, "-B", "-m", "unittest", *CONFORMANCE_MODULES, "-q"]
            # The full core inventory had become the >120s serial critical path
            # on Linux/Python 3.14. Partition modules, never individual tests or
            # acceptance requirements; each command receives a distinct home.
            core_partitions = [core_modules[::2], core_modules[1::2]]
            core_commands = [[sys.executable, "-B", "-m", "unittest", *part, "-q"]
                             for part in core_partitions if part]
            first_phase = core_commands + commands[1:4] + [commands[-1], external]
            for offset, phase in ((0, first_phase), (len(first_phase), commands[4:-1])):
                failed = run_phase(phase, env, temp, started + 120, offset)
                if failed is not None:
                    print(json.dumps({"passed": False, "command": failed}))
                    return 1
            elapsed = time.monotonic() - started
            passed = elapsed <= 120
            print(json.dumps({"passed": passed, "seconds": round(elapsed, 3),
                              "python": sys.version.split()[0], "nodePython": env["PYTHON"],
                              "budgetSeconds": 120, "modules": MODULES + NATIVE_MODULES}))
            return 0 if passed else 1
        except subprocess.TimeoutExpired:
            print(json.dumps({"passed": False, "reason": "120-second budget exceeded"}))
            return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validator-path', type=Path,
                        help='absolute development dependency root for offline jsonschema validation only')
    args = parser.parse_args()
    if args.validator_path is not None and (not args.validator_path.is_absolute() or not args.validator_path.is_dir()):
        parser.error('--validator-path must be an existing absolute directory')
    raise SystemExit(main(validator_path=args.validator_path))
