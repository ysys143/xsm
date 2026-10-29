"""Transparent stdio forwarding, with one actual inbox response withheld.

No product-state imports/writes, identity registration, constructed tool output,
ACK, reply, index repair or parent-mediated request body forwarding.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(sys.argv[1])
SOURCE = Path(sys.argv[2])
FAULT = sys.argv[3] == 'fault'
requests = {}
blocked = threading.Event()


def write(name, data):
    target = ROOT / name
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    target.chmod(0o600)


def start(pid):
    return subprocess.run(['ps', '-o', 'lstart=', '-p', str(pid)],
                          capture_output=True, text=True).stdout.strip() or None


def log(name, value):
    with (ROOT / name).open('a') as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + '\n')
        stream.flush()


server = subprocess.Popen([sys.executable, '-m', 'xsm', 'mcp'],
                          cwd=str(SOURCE), env=dict(os.environ), stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=(ROOT / 'server.stderr').open('w'),
                          text=True, bufsize=1)
write('handles.json', {'proxy_pid': os.getpid(), 'proxy_lstart': start(os.getpid()),
                       'server_pid': server.pid, 'server_lstart': start(server.pid),
                       'source_entrypoint': str(SOURCE / 'hooks/xsm-mcp.py')})


def output():
    for line in server.stdout:
        message = json.loads(line)
        request = requests.get(message.get('id'), {})
        params = request.get('params') or {}
        name = params.get('name')
        log('server-wire.jsonl', message)
        claims = []
        if name == 'xsm_inbox':
            for item in (message.get('result') or {}).get('content', []):
                if item.get('type') == 'text':
                    try:
                        claims.extend(json.loads(item['text']).get('claims', []))
                    except (ValueError, TypeError):
                        pass
        if FAULT and claims and not blocked.is_set():
            blocked.set()
            write('withheld-response.json', message)
            write('fault-observed.json', {'at': time.time(), 'tool': name,
                  'actual_request': request, 'claims': claims,
                  'response_sha256': hashlib.sha256(line.encode()).hexdigest(),
                  'response_forwarded_bytes': 0, 'synthetic_result': False})
            while True:
                time.sleep(.1)
        sys.stdout.write(line)
        sys.stdout.flush()
        log('forwarded.jsonl', {'id': message.get('id'), 'tool': name,
                               'bytes': len(line.encode()),
                               'sha256': hashlib.sha256(line.encode()).hexdigest()})


thread = threading.Thread(target=output, daemon=True)
thread.start()
try:
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('method') == 'tools/call':
            requests[message.get('id')] = message
        log('client-wire.jsonl', message)
        server.stdin.write(line)
        server.stdin.flush()
finally:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    write('proxy-exit.json', {'server_returncode': server.poll()})
