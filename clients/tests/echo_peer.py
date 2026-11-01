"""Disposable v1 contract peer. No xsm imports, state, network, or filesystem I/O."""

import json
import os
import signal
import sys
import time


MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"
HANDLE = "opaque/세션:one"
if MODE == "stubborn":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)


def send(message):
    frame = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    # Force a multi-byte UTF-8 character across writes.
    split = frame.find("세".encode("utf-8")) + 1
    if split > 0:
        os.write(1, frame[:split])
        time.sleep(0.003)
        frame = frame[split:]
    # Large frames can exceed one os.write's capacity.
    while frame:
        frame = frame[os.write(1, frame):]


def reply(request, result):
    send({"jsonrpc": "2.0", "id": request["id"], "result": result})


def error(request, code, message, data=None):
    send({"jsonrpc": "2.0", "id": request["id"],
          "error": {"code": code, "message": message, "data": data}})


held = []
initialized = False
for line in sys.stdin.buffer:
    request = json.loads(line)
    method, params = request["method"], request["params"]
    assert request["jsonrpc"] == "2.0"
    if not initialized:
        assert method == "initialize" and params == {"protocolVersion": "1"}
        if MODE == "init-error":
            error(request, -32001, "unsupported version", {"supported": []})
        elif MODE == "init-eof":
            break
        elif MODE == "init-wrong-version":
            reply(request, {"protocolVersion": "2"})
        elif MODE == "init-missing-version":
            reply(request, {})
        elif MODE == "init-nonobject":
            reply(request, ["1"])
        else:
            reply(request, {"protocolVersion": "1"})
        initialized = True
        continue
    if method == "test.pair":
        held.append(request)
        if len(held) == 2:
            if MODE == "eof":
                break
            invalid = {
                "malformed": b"{bad json}\n",
                "malformed-noisy": b"{bad json}\n" + b"x" * 300_000 + b"\n",
                "truncated": b'{"jsonrpc":"2.0"',
                "utf8": b'\xff\n',
                "bad-response": b'{"jsonrpc":"2.0","id":"x","result":1,"error":null}\n',
                "bad-error": b'{"jsonrpc":"2.0","id":"x","error":{"code":true,"message":"bad"}}\n',
                "peer-request": b'{"jsonrpc":"2.0","id":"host","method":"decision.response","params":{}}\n',
            }.get(MODE)
            if invalid:
                while invalid:
                    invalid = invalid[os.write(1, invalid):]
                if MODE != "truncated":
                    # Exercise automatic cleanup of a living, invalid peer.
                    for _ in sys.stdin.buffer:
                        pass
                break
            for item in reversed(held):
                reply(item, item["params"])
            held.clear()
    elif method == "test.hold":
        held.append(request)
    elif method == "test.error":
        error(request, -32042, "expected failure", {"detail": "세부"})
    elif method == "test.large":
        reply(request, "세" * 100_000)
    elif method == "test.stderr":
        sys.stderr.buffer.write(b'{"jsonrpc":"2.0","id":"fake","result":false}\n' +
                                ("진단" * 50_000).encode("utf-8"))
        sys.stderr.buffer.flush()
        reply(request, "stdout only")
    elif method == "test.final":
        reply(request, {"final": True})
        break
    elif method == "session.open":
        assert set(params) == {"runtime", "profile", "conversation", "cwd", "capabilities"}
        assert isinstance(params["capabilities"], list)
        reply(request, {"session": HANDLE, "generation": 7, "extra": "preserved"})
    elif method in {"session.update", "session.close", "operation.call", "events.subscribe", "delivery.report"}:
        assert params["session"] == HANDLE
        if method == "operation.call":
            assert set(params) == {"session", "operation", "arguments"}
        if method == "delivery.report":
            assert set(params) == {"session", "id", "state"}
        if method == "events.subscribe":
            # Notification can precede its subscription response.
            send({"jsonrpc": "2.0", "method": "events/available",
                  "params": {"session": HANDLE, "ids": ["delivery-세"]}})
        reply(request, params)
    else:
        reply(request, params)

if MODE == "stubborn":
    while True:
        time.sleep(10)
