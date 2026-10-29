"""Durable installation flow binding and read-only capability evidence.

No login, permission change, installation, active probe, agent wake or session
termination is performed here. Remote adapters can record completion only for
the active flow id + exact target + generation. A waiter timing out does not
cancel its flow; starting a replacement flow invalidates older finishers.

Installation evidence and a successful model roundtrip are separate observations.
D11 support, automatic replacement and backup retention promises are unchanged.
State is UID-private and inside the existing same-uid trust boundary.
"""
from __future__ import annotations

import copy
import contextlib
import hashlib
import json
import os
import re
import stat
import sys
import time
import uuid

from . import install, paths

__all__ = ["begin", "read", "record", "report", "installation_readback", "doctor_report",
           "installation", "SetupError", "StaleFlowError"]
_ID = re.compile(r"[0-9a-f]{32}\Z")
_STEPS = frozenset(("runtime", "harness", "login", "membership", "account",
                    "existing-session", "first-roundtrip"))
_STATUSES = frozenset(("pending", "succeeded", "failed", "unknown"))
_CAPABILITIES = ("identity", "idle-wake", "during-work", "question-reply",
                 "fyi", "human-decision", "attachments", "resume")


class SetupError(ValueError):
    pass


class StaleFlowError(SetupError):
    """An old finisher must not update a replacement flow or another home."""


def _target(target):
    if not isinstance(target, dict) or not target:
        raise SetupError("target must be a nonempty mapping")
    allowed = ("runtime", "home", "backend", "account", "team")
    if any(key not in allowed or not isinstance(value, str) or not value.strip()
           for key, value in target.items()):
        raise SetupError("invalid setup target fields")
    out = dict(target)
    if "runtime" in out and out["runtime"] not in ("claude", "codex"):
        raise SetupError("unknown setup runtime")
    if "home" in out:
        out["home"] = os.path.realpath(os.path.expanduser(out["home"]))
    return out


def _encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _key(target):
    return hashlib.sha256(_encoded(target)).hexdigest()


def _pending(target):
    return paths.path("setup", "targets", _key(_target(target)) + ".json")


def _flow(flow_id):
    if not isinstance(flow_id, str) or not _ID.fullmatch(flow_id):
        raise SetupError("invalid flow id")
    return paths.path("setup", "flows", flow_id + ".json")


def _private_read(filename):
    try:
        fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SetupError("setup state cannot be opened: " + type(exc).__name__) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise SetupError("setup state is not a UID-private regular file")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = None
            value = json.load(stream)
        if not isinstance(value, dict):
            raise SetupError("invalid setup state")
        return value
    except (OSError, ValueError) as exc:
        if isinstance(exc, SetupError):
            raise
        raise SetupError("setup state cannot be read: " + type(exc).__name__) from exc
    finally:
        if fd is not None:
            os.close(fd)


def _active(target):
    pointer = _private_read(_pending(target))
    if pointer is None:
        return None
    if (type(pointer.get("v")) is not int or pointer["v"] != 1 or pointer.get("target") != target or
            type(pointer.get("generation")) is not int or pointer["generation"] < 1):
        raise SetupError("invalid setup pointer")
    _flow(pointer.get("flow_id"))
    return pointer


def _bound(target, flow_id, generation):
    pointer = _active(target)
    if (pointer is None or pointer["flow_id"] != flow_id or
            type(generation) is not int or pointer["generation"] != generation):
        raise StaleFlowError("setup-flow-replaced: flow id, target or generation changed")
    return pointer


def begin(target: dict, *, steps=("runtime", "harness", "first-roundtrip"),
          optional_steps=()) -> dict:
    """Start a new generation, retaining earlier flows and their local evidence."""
    target = _target(target)
    steps, optional_steps = tuple(steps), tuple(optional_steps)
    if (not steps or len(set(steps)) != len(steps) or any(step not in _STEPS for step in steps) or
            any(step not in steps for step in optional_steps)):
        raise SetupError("invalid setup steps")
    pending = _pending(target)
    with install._target_lock(pending):
        old = _active(target)
        revision = install.file_revision(pending)
        flow_id = uuid.uuid4().hex
        generation = old["generation"] + 1 if old else 1
        state = {"v": 1, "flow_id": flow_id, "target": target, "generation": generation,
                 "created_at": time.time(), "updated_at": time.time(), "status": "pending",
                 "local_ready": False,
                 "steps": {step: {"status": "pending", "optional": step in optional_steps}
                           for step in steps}}
        install._cas_bytes(_flow(flow_id), _encoded(state), "missing", mode=0o600)
        pointer = {key: state[key] for key in ("v", "flow_id", "target", "generation")}
        install._cas_bytes(pending, _encoded(pointer), revision, mode=0o600)
        return copy.deepcopy(state)


def read(target: dict) -> dict | None:
    target = _target(target)
    with install._target_lock(_pending(target)):
        return _read_current(target)


def _read_current(target):
    revision = install.file_revision(_pending(target))
    pointer = _active(target)
    if pointer is None:
        return None
    state = _private_read(_flow(pointer["flow_id"]))
    if (state is None or any(state.get(key) != value for key, value in pointer.items()) or
            not isinstance(state.get("steps"), dict) or
            state.get("status") not in ("pending", "succeeded", "failed", "partial")):
        raise SetupError("setup flow and pointer do not match")
    for step, item in state["steps"].items():
        if (step not in _STEPS or not isinstance(item, dict) or
                not isinstance(item.get("status"), str) or item["status"] not in _STATUSES or
                type(item.get("optional")) is not bool):
            raise SetupError("invalid saved setup step")
    if install.file_revision(_pending(target)) != revision:
        raise StaleFlowError("setup pointer changed during readback")
    return state


def _evidence(evidence):
    # No raw errors, credentials, invitations, body, argv or free-form messages.
    allowed = {"request_id", "reply_to", "reply_id", "conversation", "received", "replied", "home_match",
               "fixture", "runtime_version", "api_version", "error_code", "observation"}
    if not isinstance(evidence, dict) or any(key not in allowed for key in evidence):
        raise SetupError("unsupported setup evidence fields")
    for key, value in evidence.items():
        if key in ("received", "replied", "home_match", "fixture"):
            if type(value) is not bool:
                raise SetupError("setup evidence flag must be boolean")
        elif not isinstance(value, str) or len(value) > 128 or not re.fullmatch(r"[A-Za-z0-9_.:/-]*", value):
            raise SetupError("setup evidence identifiers must be bounded tokens")
    return copy.deepcopy(evidence)


def record(flow_id: str, target: dict, generation: int, step: str,
           status: str, *, evidence=None) -> dict:
    """Persist a response only after rechecking its binding just before save.

    Login success does not imply membership, harness trust or a first reply.
    Optional account failure does not erase successful local setup steps.
    This method records evidence; it does not write credentials or approve tools.
    """
    target = _target(target)
    if step not in _STEPS or status not in _STATUSES:
        raise SetupError("invalid setup step or status")
    evidence = _evidence({} if evidence is None else evidence)
    if step == "first-roundtrip" and status == "succeeded" and not (
            evidence.get("request_id") and evidence.get("reply_to") == evidence["request_id"] and
            all(evidence.get(key) is True for key in ("received", "replied", "home_match"))):
        raise SetupError("first roundtrip requires correlated request, receipt, reply and home evidence")
    pending = _pending(target)
    with install._target_lock(pending):
        _bound(target, flow_id, generation)
        pointer_revision = install.file_revision(pending)
        state = read(target)
        if step not in state["steps"]:
            raise SetupError("step is not part of this flow")
        filename = _flow(flow_id)
        revision = install.file_revision(filename)
        state["steps"][step].update(status=status, evidence=evidence)
        required = [item["status"] for item in state["steps"].values() if not item["optional"]]
        optional_failed = any(item["optional"] and item["status"] == "failed" for item in state["steps"].values())
        state["status"] = ("failed" if "failed" in required else
                           ("partial" if optional_failed else "succeeded")
                           if required and all(item == "succeeded" for item in required) else "pending")
        state["local_ready"] = all(state["steps"].get(key, {}).get("status") == "succeeded"
                                   for key in ("runtime", "harness"))
        state["updated_at"] = time.time()
        def still_current():
            _bound(target, flow_id, generation)
            if install.file_revision(pending) != pointer_revision:
                raise StaleFlowError("setup pointer changed before completion save")
        install._cas_bytes(filename, _encoded(state), revision, mode=0o600, check=still_current)
        return copy.deepcopy(state)


@contextlib.contextmanager
def installation(flows):
    """Fence actual installer commits as well as completion records.

    Cooperating replacement flows wait for an in-flight installation. A direct
    pending-file replacement is rechecked at each commit and cannot let an old
    result overwrite a new flow. This does not authenticate same-uid callers.
    """
    def check():
        for flow in flows:
            _bound(flow["target"], flow["flow_id"], flow["generation"])
    with contextlib.ExitStack() as stack:
        for pending in sorted({_pending(flow["target"]) for flow in flows}):
            stack.enter_context(install._target_lock(pending))
        stack.enter_context(install.setup_write_guard(check))
        yield


def installation_readback(target, *, mcp_requested=False, plugin_allowed=False):
    """Read configuration after the real CLI operation; never infer a model turn."""
    target = _target(target)
    home, runtime = target["home"], target["runtime"]
    root, expected = install.runtime_root(), install.runtime_root(planned=True)
    observed_digest = install.runtime_digest(root, install.SNAPSHOT_FILES)
    wanted_digest = install.runtime_digest(install.REPO, install.SNAPSHOT_FILES)
    runtime_ok = (observed_digest is not None and observed_digest == wanted_digest and
                  os.path.realpath(root) == os.path.realpath(expected))
    plugin = install.plugin_installed(home) if plugin_allowed else None
    plan = install.plan(home, runtime, root=expected)
    harness_ok = bool(plan.get("exists")) and not plan.get("error") and all(
        action["action"] == "keep" for action in plan.get("actions", []))
    if plugin:
        plugin_root = install.plugin_root(home)
        runtime_ok = bool(plugin_root and install.runtime_digest(plugin_root, install.SNAPSHOT_FILES))
        harness_ok = (install.codex_plugin(home) is not None if runtime == "codex"
                      else not install.plugin_missing_hooks(home))
    mcp = "unknown"
    if mcp_requested and not plugin:
        mcp = "observed" if install.mcp_state(home, runtime) == "current" else "not-observed"
        harness_ok = harness_ok and mcp == "observed"
    ownership = install.component_manifest(home, runtime)
    supply = install.supply_report(root)
    return {"runtime": "succeeded" if runtime_ok else "unknown" if plugin else "failed",
            "harness": "succeeded" if harness_ok else "unknown" if plugin else "failed",
            "mcp": mcp, "ownership": ownership, "supply": supply,
            "integration": "plugin" if plugin else "direct", "first_roundtrip": "unknown"}


def _roundtrip_evidence(target,state):
    from . import questions
    step=(state.get('steps') or {}).get('first-roundtrip') or {}
    proof=step.get('evidence') or {}
    if step.get('status')!='succeeded' or not proof.get('conversation') or not proof.get('reply_id'):
        return None
    receiver=dict(target,session_id=proof['conversation'])
    value=questions.status(receiver,proof.get('request_id'))
    if (value.get('created_at') or 0)<state['created_at']:return None
    matched=next((r for r in value.get('replies',[]) if r['id']==proof['reply_id']),None)
    if not matched or matched.get('received_at',0)<state['created_at']:return None
    return dict(proof,observed_at=matched['received_at'])


def observe_roundtrip(receiver,sender,request_id,reply_id):
    """A new correlated peer reply is communication evidence, never approval."""
    from . import questions
    target=_target({'runtime':receiver.get('runtime'),'home':receiver.get('home')})
    state=read(target)
    if not state or not state.get('local_ready') or 'first-roundtrip' not in state['steps']:return False
    if _roundtrip_evidence(target,state):return True
    if not questions.expects_reply(receiver,sender,request_id):return False
    value=questions.status(receiver,request_id)
    if (value.get('created_at') or 0)<state['created_at']:return False
    reply=next((r for r in value.get('replies',[]) if r['id']==reply_id),None)
    if not reply or reply.get('received_at',0)<state['created_at']:return False
    fixture=any(bool(item.get('evidence',{}).get('fixture')) for item in state['steps'].values())
    record(state['flow_id'],target,state['generation'],'first-roundtrip','succeeded',evidence={
        'request_id':request_id,'reply_to':request_id,'reply_id':reply_id,'conversation':receiver['session_id'],
        'received':True,'replied':True,'home_match':True,'fixture':fixture,'observation':'correlated-peer-reply'})
    return True


def doctor_report(base):
    """Join existing doctor readbacks with passive, home-bound process facts.

    A live PID with matching start time observes that process only. A socket
    file observes filesystem presence only; no message or socket connection is
    sent. Capability/LLM reply evidence remains unknown here.
    """
    from . import identity, registry
    try:
        records = registry.raw_records()
    except (OSError, ValueError):
        records = []
    homes = list(base.get("homes", []))
    seen = {(item["runtime"], os.path.realpath(item["path"])) for item in homes}
    pending_dir = paths.path("setup", "targets")
    if os.path.isdir(pending_dir):
        for name in sorted(os.listdir(pending_dir)):
            if not name.endswith(".json"):
                continue
            pointer = _private_read(os.path.join(pending_dir, name))
            target = pointer.get("target") if isinstance(pointer, dict) else None
            if not isinstance(target, dict) or not all(isinstance(target.get(key), str) for key in ("runtime", "home")):
                continue
            target = _target(target)
            key = (target["runtime"], target["home"])
            if key not in seen:
                homes.append({"runtime": target["runtime"], "path": target["home"]})
                seen.add(key)
    observations = []
    for home in homes:
        target = _target({"runtime": home["runtime"], "home": home["path"]})
        observation = dict(target)
        trust = (base.get("codex_trust") or {}).get(home["path"])
        if isinstance(trust, dict) and trust:
            observation["trust"] = all(value is True for value in trust.values())
        for rec in records:
            if (rec.get("runtime") != target["runtime"] or not isinstance(rec.get("home"), str) or
                    os.path.realpath(rec["home"]) != target["home"]):
                continue
            pid, started = rec.get("pid"), rec.get("lstart")
            if pid and started:
                current = identity.lstart(pid)
                if current:
                    observation["process"] = current == started
                    observation["home_match"] = observation["process"]
            socket = rec.get("socket")
            if isinstance(socket, str) and socket:
                try:
                    observation["socket"] = stat.S_ISSOCK(os.stat(socket).st_mode)
                except OSError:
                    observation["socket"] = False
        observations.append(observation)
    result = report(homes, observations=observations)
    for row, home in zip(result["homes"], homes):
        state=None
        try:
            state = _read_current(_target({"runtime": home["runtime"], "home": home["path"]}))
            row["flow"] = ({"flow_id": state["flow_id"], "generation": state["generation"],
                            "status": state["status"], "local_ready": state.get("local_ready", False),
                            "steps": {key: value["status"] for key, value in state["steps"].items()}}
                           if state else None)
        except (OSError, ValueError, KeyError):
            row["flow"] = {"status": "unavailable"}
        row["process_evidence"] = "pid-and-start-time-readback"
        row["socket_evidence"] = "filesystem-readback"
        proof=_roundtrip_evidence(_target({'runtime':home['runtime'],'home':home['path']}),state) if state else None
        row['first_roundtrip']=('fixture' if proof.get('fixture') else 'observed') if proof else 'unknown'
        if proof:row['first_roundtrip_observed_at']=proof['observed_at']
    return result


def _observation(observations, target):
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        # Callers supply locally observed evidence, bound to this exact home.
        home = observation.get("home")
        if (observation.get("runtime") == target["runtime"] and isinstance(home, str) and
                os.path.realpath(os.path.expanduser(home)) == target["home"]):
            return observation
    return {}


def report(homes=None, *, observations=()) -> dict:
    """Read-only, redacted diagnostic API for doctor. No active test is implied.

    observations must be local probe results, not peer claims. Public output
    contains fixed statuses and hashed home identities; it never returns source
    configs, commands, token values, errors, invitation URLs or message bodies.
    Missing service/socket/trust/reply evidence stays unknown, regardless of
    static tool catalogs or installed files.
    """
    if homes is None:
        from . import config
        homes = config.homes()
    result = {"status": "observational",
              "active_probe": "not-run", "homes": [], "supply": install.supply_report(),
              "observed_environment": {"python": sys.version.split()[0], "platform": sys.platform}}
    for home in homes:
        target = _target({"runtime": home["runtime"], "home": home["path"]})
        observed = _observation(observations, target)
        try:
            planned = install.plan(target["home"], target["runtime"], root=install.REPO)
            configured = "invalid" if planned.get("error") else "present" if planned.get("exists") else "absent"
        except (OSError, ValueError):
            configured = "unknown"
        row = {"runtime": target["runtime"], "home_id": _key(target), "settings": configured,
               "trust": "unknown", "process": "unknown", "socket": "unknown",
               "home_match": "unknown", "mcp": "unknown",
               "capabilities": {key: "unknown" for key in _CAPABILITIES},
               "first_roundtrip": "not-observed"}
        for key in ("trust", "process", "socket", "home_match", "mcp"):
            value = observed.get(key)
            if type(value) is bool:
                row[key] = "observed" if value else "not-observed"
        for key in ("runtime_version", "api_version"):
            value = observed.get(key)
            row[key] = value if isinstance(value, str) and len(value) < 64 and re.fullmatch(r"v?[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9_.-]+)?", value) else "unknown"
        try:
            row["ownership"] = install.component_manifest(target["home"], target["runtime"])["items"]
        except (OSError, ValueError, KeyError, TypeError):
            row["ownership"] = "unknown"
        for key in _CAPABILITIES:
            value = observed.get("capabilities", {}).get(key) if isinstance(observed.get("capabilities"), dict) else None
            if value in ("observed", "unsupported", "failed", "unknown"):
                row["capabilities"][key] = value
        reply = observed.get("roundtrip")
        if (isinstance(reply, dict) and isinstance(reply.get("request_id"), str) and bool(reply["request_id"]) and
                reply.get("reply_to") == reply["request_id"] and reply.get("received") is True and
                reply.get("replied") is True and observed.get("home_match") is True):
            row["first_roundtrip"] = "fixture" if reply.get("fixture") is True else "observed"
        result["homes"].append(row)
    return result
