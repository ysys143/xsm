"""Bounded real OpenAI subscription relay; no token access or response synthesis."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request


class OpenAiSubscriptionRelay:
    UPSTREAM = 'http://127.0.0.1:10100/v1/chat/completions'
    CATALOG = 'http://127.0.0.1:10100/v1/models'

    def __init__(self, output, model, *, max_requests=8):
        if type(max_requests) is not int or not 1 <= max_requests <= 8:
            raise ValueError('request limit must be 1..8')
        self.model, self.max_requests = model, max_requests
        self.output = Path(output)
        self.lock = threading.Lock()
        self.calls = self.forwarded = 0
        self.response_models, self.active = set(), set()
        self.limit_failure = False
        self.started = time.monotonic()
        self.deadline = self.started + 105
        self.log = Path(output) / 'subscription-relay.jsonl'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        expected = {'providers.openai.authMode': 'forward',
                    'providers.openai.adapter': 'openai-responses',
                    'providers.openai.baseUrl': 'https://chatgpt.com/backend-api/codex',
                    'providers.openai.codexAccountMode': 'pool'}
        observed = {}
        for field, value in expected.items():
            result = subprocess.run(['ocx', 'config', 'get', field], capture_output=True,
                                    text=True, timeout=8)
            observed[field] = result.stdout.strip()
            if result.returncode or observed[field] != value:
                raise ValueError('existing OpenAI subscription condition mismatch: ' + field)
        with self.opener.open(self.CATALOG, timeout=8) as response:
            catalog = json.load(response)
        allowlist = [row['id'] for row in catalog.get('data', [])
                     if isinstance(row, dict) and row.get('owned_by') == 'openai'
                     and isinstance(row.get('id'), str)]
        if model not in allowlist:
            raise ValueError('exact model absent from live OpenAI catalog')
        metadata = {'verifiedConditions': observed, 'liveOpenAiAllowlist': allowlist,
                    'requestedModel': model, 'authorization': 'fixed local placeholder only',
                    'maxRequests': max_requests, 'inferenceRetry': False}
        (Path(output) / 'subscription-route-verification.json').write_text(json.dumps(metadata, indent=2) + '\n')
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                if self.path != '/v1/chat/completions':
                    self.send_error(404)
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 4 * 1048576:
                        raise ValueError()
                    body = self.rfile.read(size)
                    params = json.loads(body)
                    if not isinstance(params, dict) or params.get('model') != relay.model:
                        raise ValueError()
                except (ValueError, TypeError):
                    self.send_error(400, 'exact allowlisted model and bounded request required')
                    return
                with relay.lock:
                    relay.calls += 1
                    if relay.limit_failure or relay.forwarded >= relay.max_requests or time.monotonic() >= relay.deadline:
                        self.send_error(429, 'probe stopped; no further upstream calls')
                        return
                    relay.forwarded += 1
                    serial = relay.forwarded
                    relay.active.add(serial)
                    declarations = params.get('tools') or []
                    tool_summary = [{'name': (t.get('function') or t).get('name'), 'strict': (t.get('function') or t).get('strict')} for t in declarations if isinstance(t, dict)]
                    (relay.output / ('request-%02d.json' % serial)).write_text(json.dumps(params, ensure_ascii=False, indent=2) + '\n')
                    (relay.output / ('request-%02d-tools.json' % serial)).write_text(json.dumps(tool_summary, indent=2) + '\n')
                    relay._record_locked({'phase': 'started', 'request': serial, 'requestedModel': relay.model})
                request = urllib.request.Request(relay.UPSTREAM, body, method='POST', headers={
                    'Content-Type': 'application/json', 'Authorization': 'Bearer local-proxy-placeholder'})
                observation = {'request': serial, 'requestedModel': relay.model}
                try:
                    try:
                        response = relay.opener.open(request, timeout=max(1, min(75, relay.deadline - time.monotonic())))
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        payload = response.read(8 * 1048576 + 1)
                        status = response.code
                        content_type = response.headers.get('Content-Type', 'application/json')
                    if len(payload) > 8 * 1048576:
                        raise ValueError('upstream response exceeded bound')
                    models = set()
                    frames = [payload] if 'event-stream' not in content_type else [
                        line[6:] for line in payload.splitlines() if line.startswith(b'data: ')]
                    for frame in frames:
                        try:
                            value = json.loads(frame)
                        except (ValueError, UnicodeError):
                            continue
                        name = value.get('model') if isinstance(value, dict) else None
                        if isinstance(name, str) and 0 < len(name) <= 256 and all(ord(c) >= 32 for c in name):
                            models.add(name)
                    limit = status in (401, 402, 403, 429) or (status >= 400 and bool(re.search(
                        rb'quota|usage.limit|rate.limit|credit|insufficient|out.of.extra', payload, re.I)))
                    observation.update(phase='response', httpStatus=status, responseModels=sorted(models),
                                       responseBytes=len(payload), limitFailure=limit)
                    with relay.lock:
                        relay.limit_failure |= limit
                        relay.response_models.update(models)
                        relay.active.discard(serial)
                        relay._record_locked(observation)
                    self.send_response(status)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (OSError, ValueError, TimeoutError) as error:
                    observation.update(phase='relay-error', failureType=type(error).__name__, upstreamState='unknown')
                    with relay.lock:
                        relay._record_locked(observation)
                    self.send_error(502, 'real upstream unavailable; no automatic retry')
                finally:
                    with relay.lock:
                        relay.active.discard(serial)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _record_locked(self, value):
        with self.log.open('a') as stream:
            stream.write(json.dumps(value) + '\n')

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        with self.lock:
            for serial in self.active:
                self._record_locked({'phase': 'observer-closed', 'request': serial, 'upstreamState': 'unknown'})
