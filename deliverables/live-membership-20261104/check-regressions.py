"""Reproduce the join regressions only in temporary source copies."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile

OUTPUT = Path(__file__).resolve().parent
REPO = OUTPUT.parents[1]
CASES = [
    ('resume-answer', ['xsm/user_answers.py'], 'f606349',
     'tests.test_user_answers.UserAnswersTest.test_resuming_after_interruption_keeps_the_exact_bound_answer'),
    ('undecided-question', ['xsm/consent.py'], 'f606349',
     'tests.test_open_consent.RequestAsReplyTest.test_request_to_show_an_approval_question_is_not_the_answer'),
    ('cli-inherited-membership', ['xsm/cli.py'], '8b0345a',
     'tests.test_worker_project_flow.WorkerProjectFlowTest.test_cli_worker_rejoining_approved_project_needs_no_new_question'),
    ('cli-parent-routing', ['xsm/cli.py'], '8b0345a',
     'tests.test_worker_project_flow.WorkerProjectFlowTest.test_cli_worker_new_project_notifies_parent_once_without_local_question'),
    ('stopped-worker-before-question', ['xsm/delegation.py', 'xsm/operations.py'], '9b2d30c',
     'tests.test_worker_project_flow.WorkerProjectFlowTest.test_ended_worker_is_rejected_before_opening_a_parent_question'),
    ('worker-ends-during-question', ['xsm/operations.py'], 'cd6d6c0',
     'tests.test_worker_project_flow.WorkerProjectFlowTest.test_worker_ending_while_form_is_open_never_starts_application'),
    ('coordinator-only-question', ['xsm/operations.py'], 'cd6d6c0',
     'tests.test_worker_project_flow.WorkerProjectFlowTest.test_new_conversation_in_joined_folder_confirms_coordinator_only'),
]
results = []
with tempfile.TemporaryDirectory(prefix='xsm-membership-red-') as directory:
    root = Path(directory).resolve()
    for name in ('xsm', 'tests', 'integrations', 'hooks', 'skills'):
        shutil.copytree(REPO / name, root / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copyfile(REPO / 'README.md', root / 'README.md')
    env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE='1')
    positive = subprocess.run(['python3', '-m', 'unittest', '-q'] + [c[-1] for c in CASES],
                              cwd=root, env=env, capture_output=True, text=True, timeout=40)
    (OUTPUT / 'regressions-positive.log').write_text(positive.stdout + positive.stderr)
    if positive.returncode:
        raise SystemExit('current source failed; no baseline regression verdict')
    for name, files, commit, test in CASES:
        originals = {file: (root / file).read_bytes() for file in files}
        for file in files:
            (root / file).write_bytes(subprocess.check_output(['git', 'show', commit + ':' + file], cwd=REPO))
        red = subprocess.run(['python3', '-m', 'unittest', test, '-q'], cwd=root,
                             env=env, capture_output=True, text=True, timeout=30)
        for file, data in originals.items():
            (root / file).write_bytes(data)
        (OUTPUT / (name + '-baseline-failure.log')).write_text(red.stdout + red.stderr)
        results.append({'case': name, 'baseline': commit, 'files': files,
                        'test': test, 'exit_code': red.returncode,
                        'detected': red.returncode == 1 and 'FAIL:' in red.stderr and 'ERROR:' not in red.stderr})
(OUTPUT / 'regressions.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
if not all(r['detected'] for r in results):
    raise SystemExit(1)
