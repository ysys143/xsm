#!/usr/bin/env python3
"""Pinned OpenCode server/autoload probe in fresh homes. No model or human UI claims."""
import argparse
import asyncio
import hashlib
import gzip
import json
import os
import platform
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "clients/python"))
from xsm_client import XsmClient


def native_binary(root, system=None, machine=None):
    system = sys.platform if system is None else system
    machine = platform.machine() if machine is None else machine
    supported = {('darwin', 'arm64'): 'opencode-darwin-arm64',
                 ('linux', 'aarch64'): 'opencode-linux-arm64',
                 ('linux', 'arm64'): 'opencode-linux-arm64',
                 ('linux', 'x86_64'): 'opencode-linux-x64',
                 ('linux', 'amd64'): 'opencode-linux-x64',
                 ('darwin', 'x86_64'): 'opencode-darwin-x64'}
    package = supported.get((system, machine.lower()))
    if package is None:
        raise ValueError('probe platform is not pinned: ' + system + '/' + machine)
    return Path(root) / 'node_modules' / package / 'bin/opencode'


class AssistantFixture:
    """Explicit scripted assistant packets, never a language model or human answer."""
    def __init__(self, output, question=None, *, warmup_inbox=False, refresh_before_ack=False, compress_requests=False):
        self.calls = 0
        self.tokens = set()
        self.lock = threading.Lock()
        self.question = question
        self.question_issued = False
        self.inbox_issued = False
        self.inbox_searched = False
        self.refresh_pending = refresh_before_ack
        self.read_refreshed_claims = False
        self.superseded_tokens = set()
        self.request_log = output / ('assistant-fixture.jsonl.gz' if compress_requests else 'assistant-fixture.jsonl')
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                available = {tool.get('function', {}).get('name') for tool in request.get('tools', [])}
                call_schema = next((tool.get('function', {}).get('parameters', {}) for tool in request.get('tools', [])
                                    if tool.get('function', {}).get('name') == 'tool_call'), {})
                lazy_native = warmup_inbox and 'tool_call' in available and 'id' in call_schema.get('required', [])
                matches = re.findall(r'tokens: (\[[^\n]+?\])', json.dumps(request.get('messages', []), ensure_ascii=False)
                                     .replace('\\"', '"').replace('\\n', '\n'))
                tokens = []
                for match in reversed(matches):
                    try:
                        tokens = json.loads(match)
                        break
                    except ValueError:
                        continue
                with fixture.lock:
                    if fixture.read_refreshed_claims:
                        for message in reversed(request.get('messages', [])):
                            if message.get('role') != 'tool' or not isinstance(message.get('content'), str):
                                continue
                            try: result = json.loads(message['content'])
                            except ValueError: continue
                            if not isinstance(result, dict) or result.get('tool', {}).get('name') != 'xsm_inbox':
                                continue
                            claims = result.get('result', {}).get('details', {}).get('claims', [])
                            observed = [claim['token'] for claim in claims if isinstance(claim, dict) and isinstance(claim.get('token'), str)]
                            if any(token not in fixture.tokens for token in observed):
                                tokens = observed
                                break
                    fresh = [token for token in tokens if token not in fixture.tokens]
                    use_tool = bool(fresh) and ('xsm_ack' in available or lazy_native)
                    tool_name, tool_args = 'xsm_ack', {'tokens': fresh}
                    if warmup_inbox and not fixture.inbox_issued and 'xsm_inbox' in available:
                        use_tool = True
                        tool_name, tool_args = 'xsm_inbox', {}
                    elif warmup_inbox and not fixture.inbox_issued and lazy_native:
                        use_tool = True
                        if not fixture.inbox_searched and 'tool_search' in available:
                            tool_name, tool_args = 'tool_search', {'queries': [
                                {'query': 'xsm_inbox', 'limit': 1}, {'query': 'xsm_ack', 'limit': 1}]}
                            fixture.inbox_searched = True
                        else:
                            tool_name, tool_args = 'tool_call', {'id': 'xsm_inbox', 'args': {}}
                    if fixture.question and not fixture.question_issued and 'xsm_decide' in available:
                        use_tool = True
                        tool_name, tool_args = 'xsm_decide', {'question': fixture.question, 'options': ['blue', 'green']}
                        fixture.question_issued = True
                    if use_tool and tool_name == 'xsm_ack' and fixture.refresh_pending:
                        fixture.refresh_pending = False
                        fixture.read_refreshed_claims = True
                        fixture.superseded_tokens.update(fresh)
                        tool_name, tool_args = ('xsm_inbox', {}) if 'xsm_inbox' in available else ('tool_call', {'id': 'xsm_inbox', 'args': {}})
                    if use_tool and (tool_name == 'xsm_inbox' or tool_name == 'tool_call' and tool_args.get('id') == 'xsm_inbox'):
                        fixture.inbox_issued = True
                    if use_tool and tool_name == 'xsm_ack' and 'xsm_ack' not in available and lazy_native:
                        tool_name, tool_args = 'tool_call', {'id': 'xsm_ack', 'args': tool_args}
                    if use_tool:
                        if tool_name == 'xsm_ack' or tool_name == 'tool_call' and tool_args.get('id') == 'xsm_ack':
                            fixture.tokens.update(fresh)
                            fixture.tokens.update(fixture.superseded_tokens)
                            fixture.superseded_tokens.clear()
                            fixture.read_refreshed_claims = False
                        fixture.calls += 1
                    with (gzip.open(fixture.request_log, 'at') if compress_requests else fixture.request_log.open('a')) as stream:
                        stream.write(json.dumps({'request': request, 'ackFixture': use_tool and (tool_name == 'xsm_ack' or
                                                 tool_name == 'tool_call' and tool_args.get('id') == 'xsm_ack'),
                                                 'toolFixture': tool_name if use_tool else None}) + '\n')
                delta = {'content': 'Explicit assistant fixture; no model inference.'}
                reason = 'stop'
                if use_tool:
                    delta = {'tool_calls': [{'index': 0, 'id': 'call_fixture_' + str(fixture.calls),
                              'type': 'function', 'function': {'name': tool_name,
                              'arguments': json.dumps(tool_args)}}]}
                    reason = 'tool_calls'
                packets = [{'id': 'fixture', 'object': 'chat.completion.chunk', 'created': int(time.time()),
                            'model': 'fixture', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                           {'id': 'fixture', 'object': 'chat.completion.chunk', 'created': int(time.time()),
                            'model': 'fixture', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': reason}]}]
                body = ''.join('data: ' + json.dumps(packet) + '\n\n' for packet in packets) + 'data: [DONE]\n\n'
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body.encode())))
                self.end_headers()
                self.wfile.write(body.encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="xsm-opencode-probe-"))
    work, home, profile, state = [temp / name for name in ("work", "home", "config/opencode", "state")]
    for path in (work, home, profile):
        path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    assistant = AssistantFixture(args.output)
    # Reuse only the explicitly supplied, privately installed pinned SDK dependencies.
    (profile / "node_modules").symlink_to(args.native_root / "node_modules", target_is_directory=True)
    # Native Config waits for dependency installation even when node_modules exists.
    # Preserve the pinned dependency manifest/lock so offline startup does not reify it.
    for name in ("package.json", "package-lock.json"):
        source = args.native_root / name
        if source.is_file():
            (profile / name).write_bytes(source.read_bytes())
    (profile / "opencode.json").write_text(json.dumps({
        "enabled_providers": ["xsm-fixture"], "model": "xsm-fixture/fixture",
        "provider": {"xsm-fixture": {"npm": "@ai-sdk/openai-compatible", "name": "No model fixture",
            "options": {"baseURL": "http://127.0.0.1:" + str(assistant.server.server_port) + "/v1"},
            "models": {"fixture": {"name": "fixture", "limit": {"context": 32000, "output": 1000}}}}},
        "permission": {"*": "deny", "xsm_ack": "allow"},
    }))
    env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR") if key in os.environ}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(temp / "config"), XDG_DATA_HOME=str(temp / "data"),
               XDG_CACHE_HOME=str(temp / "cache"), XSM_HOME=str(state), XSM_PYTHON=sys.executable,
               OPENCODE_DISABLE_DEFAULT_PLUGINS="1", OPENCODE_DISABLE_MODELS_FETCH="1",
               PYTHONDONTWRITEBYTECODE="1")
    binary = native_binary(args.native_root)
    version = subprocess.run([str(binary), "--version"], env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert version == "1.19.5", version
    command = [sys.executable, "-B", "-c",
               "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')", str(ROOT)]
    install = subprocess.run([*command, "protocol", "install", "opencode",
                              "--home", str(profile)], cwd=ROOT, env=env, capture_output=True, text=True)
    (args.output / "installation.stdout").write_text(install.stdout)
    (args.output / "installation.stderr").write_text(install.stderr)
    install.check_returncode()
    installation = json.loads(install.stdout)
    env.pop("XSM_PYTHON")
    if getattr(args, "initial_update_failure", False):
        flag = temp / "first-update-failed"
        patch = ("import os,sys;sys.path.insert(0,sys.argv[1]);from xsm import protocol\n"
                 "_original=protocol.Connection.dispatch\n"
                 "def _dispatch(self,method,params):\n"
                 " if method=='session.update':\n"
                 "  try: fd=os.open(" + repr(str(flag)) + ",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)\n"
                 "  except FileExistsError: pass\n"
                 "  else:\n   os.close(fd)\n   raise protocol.ProtocolError(-32003,'fixture initial update failure')\n"
                 " return _original(self,method,params)\n"
                 "protocol.Connection.dispatch=_dispatch\n")
        wrapper = temp / "python-update-fails-once"
        wrapper.write_text("#!" + sys.executable + "\nimport os,sys\nargs=sys.argv[1:]\n"
            "if args and args[0]=='-c' and args[-3:]==['protocol','serve','--stdio']:\n"
            " args[1]=" + repr(patch) + "+'\\nexec('+repr(args[1])+')'\n"
            "os.execv(" + repr(sys.executable) + ", [" + repr(sys.executable) + ", *args])\n")
        wrapper.chmod(0o700)
        env["XSM_PYTHON"] = str(wrapper)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = (args.output / "native.log").open("w")
    process = subprocess.Popen([str(binary), "serve", "--port", str(port), "--hostname", "127.0.0.1"],
                               cwd=work, env=env, stdout=log, stderr=log, start_new_session=True)
    base = "http://127.0.0.1:" + str(port)
    result = {"status": "running", "root": str(temp), "runtimeVersion": version,
              "python": sys.version.split()[0], "platform": sys.platform, "machine": platform.machine(), "installation": installation,
              "samplesRequested": args.samples, "samples": [], "modelConfigured": False,
              "providerFixture": "loopback scripted assistant packets; no model inference or API billing",
              "physicalHumanUiTested": False, "nativeToolExecutionTested": False,
              "measurement": "send initiation to observed stored native text; includes polling; consumption not inferred",
              "sourceSha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                  ("integrations/opencode/xsm.mjs", "xsm/host_install.py", "scripts/probe-opencode-protocol.py")}}

    def checkpoint():
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    async def request(path, body=None):
        def fetch():
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as response:
                return json.load(response)
        return await asyncio.to_thread(fetch)

    sender = None
    checkpoint()
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("native server stopped: " + str(process.returncode))
            try:
                await request("/global/health")
                break
            except OSError:
                await asyncio.sleep(.05)
        tools = await request("/experimental/tool/ids")
        result["nativeTools"] = [name for name in tools if name.startswith("xsm_")]
        assert len(result["nativeTools"]) == 21, tools
        schemas = await request("/experimental/tool?provider=xsm-fixture&model=fixture")
        (args.output / "native-tools.json").write_text(json.dumps(schemas, indent=2))
        native = await request("/session", {"title": "xsm model-free admission probe"})
        result["nativeSession"] = native["id"]
        if getattr(args, "initial_update_failure", False):
            failed = None
            for _ in range(100):
                rows = [json.loads(path.read_text()) for path in (state / "sessions").glob("*.json")]
                failed = next((row for row in rows if row.get("runtime") == "opencode" and row.get("ended_at")), None)
                if failed and flag.exists():
                    break
                await asyncio.sleep(.05)
            assert failed and flag.exists(), "failed initial registration was not cleaned up"
            await request("/session/" + native["id"] + "/message", {"noReply": True,
                "parts": [{"type": "text", "text": "Retry failed initial registration fixture"}]})
            result["initialUpdateFailure"] = {"closedBeforeRetry": True, "oldPid": failed["pid"], "ref": failed["ref"]}
        receiver = None
        for _ in range(100):
            rows = [json.loads(path.read_text()) for path in (state / "sessions").glob("*.json")]
            receiver = next((row for row in rows if row.get("runtime") == "opencode" and
                             not row.get("ended_at")), None)
            if receiver:
                break
            await asyncio.sleep(.05)
        assert receiver, "native session was not registered"
        assert os.path.realpath(receiver["protocol_root"]) == os.path.realpath(installation["runtime_root"])
        if getattr(args, "initial_update_failure", False):
            assert receiver["ref"] == failed["ref"] and receiver["protocol_generation"] != failed["protocol_generation"]
            result["initialUpdateFailure"].update(newPid=receiver["pid"], generationChanged=True)
        result["receiver"] = receiver
        if getattr(args, "crash", False) or getattr(args, "auto_reconnect", False):
            previous = receiver
            for _ in range(100):
                rows = [json.loads(path.read_text()) for path in (state / "sessions").glob("*.json")]
                ready = next((row for row in rows if row.get("pid") == previous["pid"] and
                              row.get("name") == native["title"] and not row.get("ended_at")), None)
                if ready:
                    previous = ready
                    break
                await asyncio.sleep(.025)
            assert ready, "initial host state update was not observed before crash"
            assert previous["pid"] != process.pid and os.getpgid(previous["pid"]) == process.pid, "backend is not in the probe's private process group"
            os.kill(previous["pid"], signal.SIGKILL)
            deadline = time.monotonic() + 5
            while True:
                try:
                    os.kill(previous["pid"], 0)
                except ProcessLookupError:
                    break
                assert time.monotonic() < deadline, "backend was not reaped"
                await asyncio.sleep(.01)
            if getattr(args, "auto_reconnect", False):
                automatic = None
                for _ in range(200):
                    rows = [json.loads(path.read_text()) for path in (state / "sessions").glob("*.json")]
                    automatic = next((row for row in rows if row.get("ref") == previous["ref"] and
                                     row.get("pid") != previous["pid"] and not row.get("ended_at")), None)
                    if automatic:
                        break
                    await asyncio.sleep(.025)
                assert automatic, "backend did not automatically reconnect before a native entry"
                result["automaticReconnectObservedBeforeNativeEntry"] = True
            else:
                await request("/session/" + native["id"] + "/message", {
                    "noReply": True, "parts": [{"type": "text", "text": "Native backend recovery boundary fixture"}]})
            for _ in range(100):
                rows = [json.loads(path.read_text()) for path in (state / "sessions").glob("*.json")]
                receiver = next((row for row in rows if row.get("ref") == previous["ref"] and
                                 row.get("pid") != previous["pid"] and not row.get("ended_at")), None)
                if receiver:
                    break
                await asyncio.sleep(.05)
            assert receiver and receiver["protocol_generation"] != previous["protocol_generation"], "native boundary did not re-register"
            result["backendRecovery"] = {"oldPid": previous["pid"], "newPid": receiver["pid"],
                "sameRef": receiver["ref"] == previous["ref"], "generationChanged": True,
                "trigger": "automatic transport recovery before native entry" if getattr(args, "auto_reconnect", False) else "real native chat.message boundary with noReply; no failed operation replay"}
            checkpoint()
        sender = await XsmClient.connect([*command, "protocol", "serve", "--stdio"],
                                         cwd=str(work), env=env)
        own = await sender.session_open(runtime="probe", profile="isolated", conversation="sender", cwd=str(work))
        for sample in range(args.samples):
            for _ in range(200):
                statuses = await request('/session/status')
                if statuses.get(native['id'], {'type': 'idle'})['type'] == 'idle':
                    break
                await asyncio.sleep(.01)
            else:
                raise RuntimeError('native session did not return to idle before sample ' + str(sample))
            marker = "opencode-native-admission-" + str(sample)
            started = time.monotonic()
            sent = await sender.operation_call(own["session"], "xsm_send",
                                                {"target": "ref:" + receiver["ref"], "text": marker, "wait": 0})
            messages = []
            for _ in range(150):
                messages = await request("/session/" + native["id"] + "/message?limit=1000")
                if any(marker in part.get("text", "") for message in messages for part in message["parts"]):
                    break
                await asyncio.sleep(.01)
            else:
                raise RuntimeError("message did not enter native transcript: " + marker)
            result["samples"].append({"marker": marker, "idleBeforeSend": True,
                                      "upperSeconds": time.monotonic() - started, "send": sent})
            checkpoint()
            for _ in range(200):
                messages = await request("/session/" + native["id"] + "/message?limit=1000")
                completed = [part for message in messages for part in message['parts']
                             if part.get('type') == 'tool' and part.get('tool') == 'xsm_ack'
                             and part.get('state', {}).get('status') == 'completed']
                if len(completed) >= sample + 1:
                    break
                await asyncio.sleep(.01)
            else:
                raise RuntimeError('native ACK tool did not complete for sample ' + str(sample))
            ack_output = completed[-1]['state'].get('output')
            acked = json.loads(ack_output).get('acked', [])
            assert len(acked) == 1 and ('id ' + acked[0]) in sent['text'], ack_output
            result['samples'][-1]['nativeAckOutput'] = ack_output
            checkpoint()
        result["p95UpperSeconds"] = sorted(item["upperSeconds"] for item in result["samples"])[
            max(0, int(len(result["samples"]) * .95 + .999) - 1)]
        result["status"] = "passed"
        result["latencyAcceptanceMet"] = args.samples >= 100 and result["p95UpperSeconds"] <= 1
        result["consumptionAckTested"] = True
        result["nativeToolExecutionTested"] = True
        result["assistantFixtureAckCalls"] = assistant.calls
        (args.output / "native-messages.json").write_text(json.dumps(messages, indent=2))
        print(json.dumps({key: result[key] for key in ("status", "runtimeVersion", "p95UpperSeconds")}), flush=True)
    except BaseException as error:
        result.update(status="failed", error=repr(error))
        raise
    finally:
        checkpoint()
        if sender:
            await sender.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.to_thread(process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                await asyncio.to_thread(process.wait)
        log.close()
        assistant.close()
        for path in (temp / "data").rglob("*.log"):
            (args.output / ("runtime-" + path.name)).write_bytes(path.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--initial-update-failure", action="store_true")
    parser.add_argument("--auto-reconnect", action="store_true")
    parser.add_argument("--crash", action="store_true")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    asyncio.run(asyncio.wait_for(run(args), timeout=150))
