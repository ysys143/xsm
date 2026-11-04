"""Run regression checks against six deliberately broken temporary copies."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile

OUTPUT = Path(__file__).resolve().parent
REPO = OUTPUT.parents[1]
CASES = [
    ('native-answer', 'xsm/consent.py',
     '        if data.get("tool_name") == "AskUserQuestion":\n            discard_selection_command(me, "publish")\n            discard_selection_command(me, "collaborate")',
     '        if data.get("tool_name") == "AskUserQuestion":\n            pass  # injected: ignore newer native answer',
     'tests.test_public_command_flow.PublicCommandFlowTest.test_later_claude_question_answer_supersedes_the_typed_command'),
    ('later-cancel', 'xsm/consent.py',
     '            discard_selection_command(me, "publish")\n            discard_selection_command(me, "collaborate")\n        # A question tool\'s answer tag:',
     '            pass  # injected: ignore superseding user turn\n        # A question tool\'s answer tag:',
     'tests.test_public_command_flow.PublicCommandFlowTest.test_later_native_user_turn_supersedes_an_unconsumed_command'),
    ('wrong-person', 'xsm/consent.py',
     'if not any(re.fullmatch(pattern, first_sentence, re.I) for pattern in (korean, original, english)):',
     'if False:  # injected: accept arbitrary repo mentions',
     'tests.test_public_command_flow.PublicCommandFlowTest.test_contact_does_not_select_a_different_named_person_or_a_question'),
    ('partial-discovery', 'xsm/consent.py',
     'if discovery.get("status") != "ok" or discovery.get("unanswered"):',
     'if False:  # injected: accept partial discovery',
     'tests.test_public_command_flow.PublicCommandFlowTest.test_partial_discovery_never_establishes_a_unique_contact_selection'),
    ('remote-command-reuse', 'xsm/connect.py',
     '        if found.scope:\n            consent.take_selection_command(sender, "collaborate", binding)',
     '        if found.scope:  # injected: leave old command reusable',
     'tests.test_network_interfaces.NetworkInterfacesTest.test_typed_remote_connect_is_consumed_even_when_scope_already_exists'),
    ('remote-unknown', 'xsm/directory.py',
     '            elif title is None or summary is None:\n                result.update(status="unknown", reason="native_filter_unknown")',
     '            elif title is None or summary is None:\n                pass  # injected: hide unknown metadata',
     'tests.test_network_interfaces.NetworkInterfacesTest.test_remote_query_preserves_unknown_task_metadata_when_no_match_is_proven'),
]

results = []
with tempfile.TemporaryDirectory(prefix='xsm-basic-red-') as folder:
    base = Path(folder)
    for directory in ('xsm', 'tests', 'integrations'):
        shutil.copytree(REPO / directory, base / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    env = dict(os.environ, PYTHONPATH=str(base), PYTHONDONTWRITEBYTECODE='1')
    positive = subprocess.run(['python3', '-m', 'unittest', '-q'] + [c[-1] for c in CASES],
                              cwd=base, env=env, text=True, capture_output=True, timeout=30)
    (OUTPUT / 'mutation-positive.log').write_text(positive.stdout + positive.stderr)
    if positive.returncode:
        raise SystemExit('temporary-copy positive checks failed; no mutation verdict')
    for name, file, old, new, test in CASES:
        p = base / file
        source = p.read_text()
        assert old in source, name
        p.write_text(source.replace(old, new, 1))
        result = subprocess.run(['python3', '-m', 'unittest', test, '-q'], cwd=base,
                                env=env, text=True, capture_output=True, timeout=20)
        p.write_text(source)
        (OUTPUT / (name + '-red.log')).write_text(result.stdout + result.stderr)
        detected = result.returncode == 1 and 'FAIL:' in result.stderr and 'ERROR:' not in result.stderr
        results.append(dict(mutation=name, test=test, exit_code=result.returncode, detected=detected))
(OUTPUT / 'mutation-results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
if not all(r['detected'] for r in results):
    raise SystemExit(1)
