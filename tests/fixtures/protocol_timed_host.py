"""Actual isolated protocol server with a post-canonical-store monotonic observer."""
import json
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from xsm import handoff

trace = Path(sys.argv[1])
fd = os.open(trace, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
original_store = handoff.store


def observed_store(receiver, message, **kwargs):
    result = original_store(receiver, message, **kwargs)
    completed = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    if message['id'].startswith('latency-'):
        os.write(fd, (json.dumps(dict(id=message['id'], storedMonotonicNs=completed)) + '\n').encode())
    return result


handoff.store = observed_store
sys.argv = [str(ROOT / 'xsm'), 'protocol', 'serve', '--stdio']
try:
    runpy.run_module('xsm', run_name='__main__')
finally:
    os.close(fd)
