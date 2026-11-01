"""Independent lifecycle fixture, not an xsm service or complete protocol implementation."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

fault = sys.argv[1] if len(sys.argv) > 1 else ""
if "OPENAI_API_KEY" in os.environ:
    raise RuntimeError("checker leaked caller credentials")

initialized = False
sessions = {}
folder = Path(os.environ["XSM_HOME"], "fixture-locks")
folder.mkdir(parents=True, exist_ok=True)


class Refused(Exception):
    def __init__(self, code):
        self.code = code


def dispatch(method, params):
    global initialized
    if method == "initialize":
        if initialized:
            raise Refused(-32600)
        if params.get("protocolVersion") != "1":
            raise Refused(-32002)
        initialized = True
        return {"protocolVersion": "1"}
    if not initialized:
        raise Refused(-32002)
    if method == "operations/list":
        return {"operations": [{"name": "fixture", "inputSchema": {"type": "object"}}]}
    if method == "session.open":
        if params["runtime"] in ("codex", "claude"):
            raise Refused(-32602)
        key = hashlib.sha256(json.dumps([params[k] for k in ("runtime", "profile", "conversation")]).encode()).hexdigest()
        file = (folder / key).open("a")
        try:
            if fault != "skip-lock":
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            file.close()
            raise Refused(-32003)
        token = uuid.uuid4().hex
        generation = "constant" if fault == "constant-generation" else uuid.uuid4().hex
        sessions[token] = file
        return {"session": token, "generation": generation, "ref": key[:6]}
    token = params.get("session")
    if token not in sessions:
        if fault == "shared-handles":
            return {"state": params.get("state")}
        raise Refused(-32001)
    if method == "session.update":
        if set(params) - {"session", "state", "name"}:
            raise Refused(-32602)
        return {"state": params.get("state", "idle")}
    if method == "session.close":
        sessions.pop(token).close()
        return {"closed": True}
    raise Refused(-32601)


try:
    for line in sys.stdin:
        request = json.loads(line)
        answer = {"jsonrpc": "2.0", "id": request["id"]}
        try:
            answer["result"] = dispatch(request["method"], request.get("params", {}))
        except Refused as error:
            answer["error"] = {"code": error.code, "message": "fixture refusal"}
        print(json.dumps(answer), flush=True)
finally:
    for file in sessions.values():
        file.close()
