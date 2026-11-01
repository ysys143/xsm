#!/usr/bin/env python3
"""Run the model-free gate on an explicit Docker endpoint, without mounting user homes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker-host', required=True)
    parser.add_argument('--docker-config', type=Path, required=True)
    parser.add_argument('--shared-dir', type=Path, required=True, help='host directory also visible to the Docker daemon')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', default='xsm-protocol-linux:node-24.22.2')
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('--output must be a new or empty directory; preserve previous evidence')
    args.output.mkdir(parents=True, exist_ok=True)
    stage = args.shared_dir.absolute() / ('protocol-' + uuid.uuid4().hex[:12])
    stage.mkdir(parents=True)
    (stage / 'output').mkdir()
    (stage / 'home').mkdir()
    archive = stage / 'source.tar'
    tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout.split(b'\0')
    count = 0
    # Release archives intentionally omit tests; use tracked working files and report the dirty state.
    with tarfile.open(archive, 'w', dereference=False) as target:
        for raw in tracked:
            if not raw:
                continue
            relative = os.fsdecode(raw)
            path = ROOT / relative
            if not path.exists() and not path.is_symlink():
                continue
            if path.name.startswith('.env') or path.suffix in ('.key', '.pem'):
                raise ValueError('credential-like tracked file requires explicit review: ' + relative)
            target.add(path, arcname=relative, recursive=False)
            count += 1
    source_commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', 'diff', '--quiet', 'HEAD'], cwd=ROOT).returncode != 0
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    env.update(HOME=str(stage / 'home'), DOCKER_CONFIG=str(args.docker_config.resolve()), DOCKER_HOST=args.docker_host)
    docker = ['docker']
    image = json.loads(subprocess.run([*docker, 'image', 'inspect', args.image], env=env, capture_output=True, text=True, check=True).stdout)[0]
    name = 'xsm-protocol-' + uuid.uuid4().hex[:16]
    command = ("tar -xf /input/source.tar -C /workspace && "
        "python3 -c 'import json,sys,platform,subprocess;print(json.dumps(dict(python=sys.version,"
        "node=subprocess.check_output([\"node\",\"--version\"],text=True).strip(),platform=platform.platform(),"
        "machine=platform.machine())))' > /output/environment.json && "
        "python3 -B scripts/check-protocol.py > /output/protocol.log 2>&1")
    result = {'passed': False, 'sourceCommit': source_commit, 'trackedWorkingTreeDirty': dirty,
        'sourceArchiveSha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'trackedFiles': count,
        'stage': str(stage), 'imageID': image['Id'], 'imageOS': image['Os'], 'imageArchitecture': image['Architecture'],
        'network': 'none', 'cpus': 2, 'memory': '3g', 'pidsLimit': 512}
    try:
        with (args.output / 'container.log').open('w') as log:
            run = subprocess.run([*docker, 'run', '--rm', '--name', name, '--network', 'none', '--cpus', '2',
                '--memory', '3g', '--pids-limit', '512', '--mount', 'type=bind,src=' + str(archive) + ',dst=/input/source.tar,readonly',
                '--mount', 'type=bind,src=' + str(stage / 'output') + ',dst=/output', args.image, 'sh', '-c', command],
                env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        result['exit'] = run.returncode
    except subprocess.TimeoutExpired:
        result['error'] = 'container deadline exceeded'
    finally:
        subprocess.run([*docker, 'rm', '-f', name], env=env, capture_output=True)
        for basename in ('environment.json', 'protocol.log'):
            filename = stage / 'output' / basename
            if filename.is_symlink():
                result['error'] = 'unsafe output symlink: ' + basename
            elif filename.is_file():
                shutil.copy2(filename, args.output / filename.name)
        text = (args.output / 'protocol.log').read_text() if (args.output / 'protocol.log').exists() else ''
        summaries = []
        for line in text.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict) and 'passed' in value:
                    summaries.append(value)
            except ValueError:
                pass
        result['gate'] = summaries[-1] if summaries else None
        result['pythonTestGroups'] = [int(n) for n in re.findall(r'Ran (\d+) tests? in', text)]
        result['nodeTests'] = [int(n) for n in re.findall(r'(?:ℹ |# )tests (\d+)', text)]
        result['passed'] = 'error' not in result and result.get('exit') == 0 and bool(result['gate'] and result['gate'].get('passed'))
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
