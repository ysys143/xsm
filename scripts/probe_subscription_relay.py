"""Bounded, credential-free observations of an existing OAuth subscription proxy.

Only development probes import this module. It is not a product transport or
an inference fixture: upstream response bytes pass through unchanged.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading
import urllib.error
import urllib.request


class SubscriptionRelay:
    UPSTREAM = 'http://127.0.0.1:10100/v1/chat/completions'
    CATALOG = 'http://127.0.0.1:10100/v1/models'

    def __init__(self, output, model, *, max_requests=8):
        if not isinstance(model, str) or not model.startswith('anthropic/') or any(ord(c) < 32 for c in model):
            raise ValueError('an exact direct Anthropic subscription model is required')
        if type(max_requests) is not int or not 1 <= max_requests <= 8:
            raise ValueError('subscription probe request budget must be 1–8')
        self.model = model
        self.max_requests = max_requests
        self.lock = threading.Lock()
        self.calls = 0
        self.forwarded = 0
        self.response_models = set()
        self.active = set()
        self.log = Path(output) / 'subscription-relay.jsonl'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.verify_subscription()
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
                        raise ValueError('bounded request required')
                    body = self.rfile.read(size)
                    params = json.loads(body)
                    if not isinstance(params, dict) or params.get('model') != relay.model:
                        raise ValueError('unapproved model')
                except (ValueError, TypeError):
                    self.send_error(400)
                    return
                with relay.lock:
                    relay.calls += 1
                    if relay.forwarded >= relay.max_requests:
                        self.send_error(429, 'subscription probe request budget exhausted')
                        return
                    relay.forwarded += 1
                    serial = relay.forwarded
                    relay.active.add(serial)
                    relay._record_locked({'phase':'started','request':serial,'requestedModel':relay.model})
                # Never forward an ambient credential or record request content.
                request = urllib.request.Request(relay.UPSTREAM, body, method='POST', headers={
                    'Content-Type': 'application/json', 'Authorization': 'Bearer local-proxy-placeholder'})
                observation = {'request': serial, 'requestedModel': relay.model}
                try:
                    try:
                        response = relay.opener.open(request, timeout=90)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        payload = response.read(8 * 1048576 + 1)
                        status = response.code
                        content_type = response.headers.get('Content-Type', 'application/json')
                    if len(payload) > 8 * 1048576:
                        raise ValueError('upstream response exceeds probe budget')
                    models = set()
                    frames = [payload] if 'event-stream' not in content_type else [
                        line[6:] for line in payload.splitlines() if line.startswith(b'data: ')]
                    for frame in frames:
                        try:
                            value = json.loads(frame)
                        except (ValueError, UnicodeError):
                            continue
                        model_id = value.get('model') if isinstance(value, dict) else None
                        if isinstance(model_id, str) and 0 < len(model_id) <= 256 and all(ord(c) >= 32 for c in model_id):
                            models.add(model_id)
                    observation.update(phase='response', httpStatus=status, responseModels=sorted(models), responseBytes=len(payload))
                    with relay.lock:
                        relay.response_models.update(models)
                        relay._record_locked(observation)
                        relay.active.discard(serial)
                    self.send_response(status)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (OSError, ValueError, TimeoutError) as error:
                    observation.update(phase='relay-error', failureType=type(error).__name__)
                    if 'httpStatus' not in observation:
                        observation['upstreamState'] = 'unknown'
                    with relay.lock:
                        relay._record_locked(observation)
                    self.send_error(502, 'subscription probe upstream unavailable')
                finally:
                    with relay.lock:
                        relay.active.discard(serial)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _record_locked(self, observation):
        with self.log.open('a') as stream:
            stream.write(json.dumps(observation) + '\n')

    def verify_subscription(self):
        # Read exactly the mode field; do not inspect credentials or change config.
        result = subprocess.run(['ocx', 'config', 'get', 'providers.anthropic.authMode'],
                                capture_output=True, text=True, timeout=10)
        if result.returncode or result.stdout.strip() != 'oauth':
            raise ValueError('existing direct Anthropic OAuth subscription route is required')
        with self.opener.open(self.CATALOG, timeout=10) as response:
            catalog = json.load(response)
        if not any(isinstance(row, dict) and row.get('id') == self.model for row in catalog.get('data', [])):
            raise ValueError('requested model is absent from the live subscription catalog')

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        with self.lock:
            for serial in sorted(self.active):
                self._record_locked({'phase':'observer-closed','request':serial,'upstreamState':'unknown'})
