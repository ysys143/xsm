#!/usr/bin/env python3
"""Observe a normal participant across an actual Linux clock adjustment; never set the clock."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main(args):
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    root = Path(tempfile.mkdtemp(prefix='xsm-participant-clock-'))
    work = root / 'work'; work.mkdir()
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    env = {k: os.environ[k] for k in ('PATH', 'LANG', 'TMPDIR') if k in os.environ}
    env.update(HOME=str(root / 'home'), XSM_HOME=str(root / 'state'), CODEX_HOME=str(root / 'codex'),
        CLAUDE_CONFIG_DIR=str(root / 'claude'), PYTHONDONTWRITEBYTECODE='1')
    spec = importlib.util.spec_from_file_location('participant_clock_checker', ROOT / 'scripts/conform-host-protocol.py')
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    observations = []; report = dict(status='running', root=str(root), modelCalls=0, clockModified=False,
        scope='actual stdio participant continuity across an observed system clock change; no native UI or model')
    peer = None
    def snapshot(pid):
        value = subprocess.run(['ps', '-o', 'lstart=', '-p', str(pid)], env={**env, 'LC_ALL': 'C', 'TZ': 'UTC'},
            capture_output=True, text=True, check=True, timeout=2).stdout.strip()
        result = dict(pid=pid, wallStart=value, wall=time.time(), monotonic=time.monotonic())
        if sys.platform.startswith('linux'):
            raw = Path('/proc/%d/stat' % pid).read_text()
            result['kernelStartTicks'] = raw.rsplit(')', 1)[1].split()[19]
            result['bootId'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            result['bootWallSeconds'] = next(l.split()[1] for l in Path('/proc/stat').read_text().splitlines() if l.startswith('btime '))
        return result
    try:
        peer = checker.Peer([sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_observed_host.py')], str(root), env, observations)
        peer.call('initialize', {'protocolVersion': '1'})
        params = dict(runtime='clock-probe', profile=str(root / 'profile'), cwd=str(work), capabilities=['user-decisions'])
        owner = peer.call('session.open', dict(params, conversation='owner'))
        member = peer.call('session.open', dict(params, conversation='member'))
        def operation(tool, **arguments):
            return peer.call('operation.call', dict(session=owner['session'], operation=tool, arguments=arguments))
        operation('xsm_team', action='create', team='clock-continuity')
        records = [json.loads(p.read_text()) for p in (root / 'state/sessions').glob('*.json')]
        record = next(r for r in records if r['ref'] == owner['ref']); assert record['pid'] == peer.process.pid
        before = snapshot(record['pid']); report.update(before=before, registeredStart=record['lstart'])
        (out / 'result.json').write_text(json.dumps(report, indent=2))
        deadline = time.monotonic() + args.wait_seconds; after = before
        while time.monotonic() < deadline:
            after = snapshot(record['pid'])
            if after['wallStart'] != before['wallStart']: break
            time.sleep(.1)
        report.update(after=after, wallStartChanged=after['wallStart'] != before['wallStart'],
            kernelStartUnchanged=(after.get('kernelStartTicks') == before['kernelStartTicks'] and after.get('bootId') == before.get('bootId')) if 'kernelStartTicks' in before else None)
        report['teamAdd'] = operation('xsm_team', action='add', team='clock-continuity', member='ref:' + member['ref'])
        report['expectedWaiting'] = report['teamAdd'].get('status') == 'waiting-for-user'
        report['status'] = ('passed' if report['wallStartChanged'] else 'not-reproduced') if report['expectedWaiting'] else 'failed'
    except BaseException as error:
        report.update(status='failed', error=repr(error))
    finally:
        report['diagnostics'] = peer.close() if peer else ''; report['observations'] = observations
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ('status', 'wallStartChanged', 'kernelStartUnchanged', 'expectedWaiting', 'error')}))
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait-seconds', type=float, default=45)
    args = parser.parse_args()
    if not 0 <= args.wait_seconds <= 60: parser.error('wait must be between zero and60 seconds')
    raise SystemExit(main(args))
