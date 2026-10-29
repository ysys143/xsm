#!/usr/bin/env python3
"""Generate the skill's messaging reference from its runtime source."""
import argparse
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from xsm.instructions import MESSAGING_GUIDE

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
target = root / "skills/xsm/references/messaging.md"
if args.check:
    if not target.exists() or target.read_text() != MESSAGING_GUIDE:
        raise SystemExit("messaging.md differs; run scripts/generate-messaging-guide.py")
    print("messaging guide matches its runtime source")
else:
    target.write_text(MESSAGING_GUIDE)
