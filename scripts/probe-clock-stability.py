#!/usr/bin/env python3
"""Read-only clock and own-process generation observations, without clock changes."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from xsm import identity

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--seconds', type=float, default=105)
args = parser.parse_args()
if not 0 < args.seconds <= 300:
    parser.error('--seconds must be in (0, 300]')
if args.output.exists():
    parser.error('output already exists; retain previous observations')
args.output.parent.mkdir(parents=True, exist_ok=True)
pid = os.getpid()
started = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
previous = (started, time.time_ns(), time.clock_gettime_ns(time.CLOCK_MONOTONIC))
last_start = identity.lstart(pid)
kernel = identity.process_start(pid)
next_process = started
report = dict(status='running', pid=pid, secondsRequested=args.seconds,
              initialStart=last_start, initialKernelStart=kernel, events=[], samples=0,
              scope='read-only host clock and own process; not a diagnosis of a different process or past failure')
while True:
    monotonic, wall = time.clock_gettime_ns(time.CLOCK_MONOTONIC), time.time_ns()
    after_wall = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    elapsed = (monotonic - started) / 1e9
    if elapsed >= args.seconds:
        break
    delta_min, delta_max = monotonic - previous[2], after_wall - previous[0]
    delta_wall = wall - previous[1]
    event = None
    if delta_wall < 0 or delta_wall < delta_min - 1_000_000 or delta_wall > delta_max + 1_000_000:
        event = dict(kind='clock-offset-change', elapsed=elapsed, wall=wall,
                     wallDeltaNs=delta_wall, monotonicDeltaMinNs=delta_min,
                     monotonicDeltaMaxNs=delta_max, clockReadSpanNs=after_wall-monotonic)
    if monotonic >= next_process:
        observed, current_kernel = identity.lstart(pid), identity.process_start(pid)
        if observed != last_start or current_kernel != kernel:
            report['events'].append(dict(kind='own-process-start-observation-change', elapsed=elapsed,
                before=last_start, after=observed, beforeKernel=kernel, afterKernel=current_kernel))
            last_start, kernel = observed, current_kernel
        next_process = monotonic + 100_000_000
    if event is not None:
        report['events'].append(event)
    report['samples'] += 1
    previous = (monotonic, wall, after_wall)
    time.sleep(.002)
report.update(status='completed', secondsObserved=elapsed,
              backwards=sum(event.get('wallDeltaNs', 0) < 0 for event in report['events']))
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: value for key, value in report.items() if key != 'events'}))
