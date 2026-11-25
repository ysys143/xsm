#!/usr/bin/env python3
"""Checks for the state-model fix plan (spec.md §5, contract.yaml).

  req.py check SM-F1        positive: the requirement's tests carry no
                            expectedFailure marker and pass
  req.py red SM-F1 ROOT     RED: in the copy at ROOT, put xsm/ back to the
                            pre-fix revision, drop the markers, run the same
                            tests; exit 0 only when they fail
  req.py check SM-REG       the whole suite passes and no state-model test
                            is still marked expectedFailure
  req.py red SM-REG ROOT    the whole suite fails on the pre-fix product code
  req.py model              fixed TLA+ models: no rule breaks
  req.py red SM-MODEL ROOT  the original models still show the breaks

Tests belong to a requirement by name: test_SM_<ID>_..., or test_SM_<ID><x>_...
for one lowercase letter x other than "r" (SM-F7 owns test_SM_F7a_*, SM-F5
does not own test_SM_F5r_*).
"""
import glob
import os
import re
import shutil
import subprocess
import sys

BASE = "2a858d3"          # 0.6.1, the code the findings were reproduced on
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MARK = re.compile(r"^\s*@unittest\.expectedFailure\s*\n", re.M)
STATECHART = os.path.expanduser(
    "~/.jstack/marketplaces/jstack/plugins/jstack/payload/skills/statechart/"
    "repos/pstack/skills/statechart/scripts/statechart")


def owns(req, name):
    rid = req[3:] if req.startswith("SM-") else req
    return re.match(r"test_SM_%s(?:[a-qs-z])?_" % re.escape(rid), name) is not None


def tests_of(root, req):
    """[(module, Class.test, marked)] for every test the requirement owns."""
    found = []
    for path in sorted(glob.glob(os.path.join(root, "tests", "test_state_model_*.py"))):
        text = open(path, encoding="utf-8").read()
        module = "tests." + os.path.basename(path)[:-3]
        cls = None
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"class (\w+)\(", line)
            if m:
                cls = m.group(1)
            m = re.match(r"\s+def (test_\w+)\(", line)
            if m and cls and owns(req, m.group(1)):
                j, marked = i - 1, False
                while j >= 0 and (lines[j].strip().startswith("@") or lines[j].strip().startswith("#")):
                    marked |= lines[j].strip() == "@unittest.expectedFailure"
                    j -= 1
                found.append((module, "%s.%s" % (cls, m.group(1)), marked))
    return found


def run(root, ids):
    cmd = [sys.executable, "-m", "unittest"] + ids
    return subprocess.run(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def all_markers(root):
    out = []
    for path in glob.glob(os.path.join(root, "tests", "test_state_model_*.py")):
        if MARK.search(open(path, encoding="utf-8").read()):
            out.append(os.path.relpath(path, root))
    return out


def revert_product(root):
    """xsm/ in the copy becomes the pre-fix revision; markers are dropped."""
    shutil.rmtree(os.path.join(root, "xsm"))
    archive = subprocess.run(["git", "-C", REPO, "archive", BASE, "xsm"], stdout=subprocess.PIPE, check=True)
    subprocess.run(["tar", "-x", "-C", root], input=archive.stdout, check=True)
    for path in glob.glob(os.path.join(root, "tests", "test_state_model_*.py")):
        text = open(path, encoding="utf-8").read()
        open(path, "w", encoding="utf-8").write(MARK.sub("", text))


def check(req):
    if req == "SM-REG":
        left = all_markers(REPO)
        if left:
            print("still marked expectedFailure:", ", ".join(left))
            return 1
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=REPO)
        return r.returncode
    if req == "SM-MODEL":
        return model(os.path.join(REPO, "deliverables", "statechart-20261125", "fixed"), expect_breaks=False)
    found = tests_of(REPO, req)
    if not found:
        print("no tests own", req)
        return 1
    marked = [t for _, t, m in found if m]
    if marked:
        print("still marked expectedFailure:", ", ".join(marked))
        return 1
    r = run(REPO, ["%s.%s" % (mod, t) for mod, t, _ in found])
    print(r.stdout[-2000:])
    return r.returncode


def red(req, root):
    if req == "SM-MODEL":
        return 0 if model(os.path.join(root, "deliverables", "statechart-20261125"), expect_breaks=True) == 0 else 1
    revert_product(root)
    if req == "SM-REG":
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=root,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    else:
        found = tests_of(root, req)
        if not found:
            print("no tests own", req)
            return 1
        r = run(root, ["%s.%s" % (mod, t) for mod, t, _ in found])
    print(r.stdout[-1500:])
    return 0 if r.returncode != 0 else 1


def model(folder, expect_breaks):
    """Run every spec/cfg pair under folder; with expect_breaks, succeed only
    if at least one rule breaks; otherwise succeed only if none does."""
    pairs = []
    for cfg in sorted(glob.glob(os.path.join(folder, "**", "*.cfg"), recursive=True)):
        if os.sep + "verify" in cfg or os.sep + "run" in cfg:
            continue
        here = os.path.dirname(cfg)
        specs = glob.glob(os.path.join(here, "*.tla"))
        views = glob.glob(os.path.join(here, "*.ts"))
        if not specs or not views:
            continue
        stem = os.path.splitext(os.path.basename(cfg))[0]
        spec = next((s for s in specs if os.path.basename(s)[:-4] == stem), specs[0])
        view = next((v for v in views if stem.lower().replace("xsm", "") in v.lower()), views[0])
        pairs.append((spec, cfg, view))
    if not pairs:
        print("no models under", folder)
        return 1
    broke = []
    for spec, cfg, view in pairs:
        out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "req-model-%d" % os.getpid(),
                           os.path.relpath(cfg, folder).replace(os.sep, "_"))
        r = subprocess.run([STATECHART, spec, "--config", cfg, "--view", view, "--out", out],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        rules = re.findall(r"^## (\w+) breaks", r.stdout, re.M)
        if rules:
            broke.append((os.path.relpath(cfg, folder), rules))
    for name, rules in broke:
        print("%s: %s" % (name, ", ".join(rules)))
    if expect_breaks:
        return 0 if broke else 1
    return 1 if broke else 0


if __name__ == "__main__":
    mode, req = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "SM-MODEL")
    if mode == "check":
        sys.exit(check(req))
    if mode == "red":
        sys.exit(red(req, os.path.abspath(sys.argv[3])))
    if mode == "model":
        sys.exit(check("SM-MODEL"))
    sys.exit(2)
