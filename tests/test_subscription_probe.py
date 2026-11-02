"""The real-model probe relay stays bounded and does not manufacture responses."""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location('subscription_probe',
    Path(__file__).resolve().parents[1] / 'scripts/probe_subscription_relay.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SubscriptionProbeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xsm-relay-test-')
        self.addCleanup(self.temp.cleanup)
        self.seen = []
        self.payload = b'data: {"model":"upstream-response-model","choices":[{"delta":{"content":"private-response"}}]}\n\ndata: [DONE]\n\n'
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                owner.seen.append((body, self.headers.get('Authorization')))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(owner.payload)))
                self.end_headers()
                self.wfile.write(owner.payload)
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        def close():
            upstream.shutdown(); upstream.server_close(); thread.join(timeout=2)
        self.addCleanup(close)
        patcher = mock.patch.object(module.SubscriptionRelay, 'UPSTREAM',
            'http://127.0.0.1:' + str(upstream.server_port) + '/v1/chat/completions')
        patcher.start(); self.addCleanup(patcher.stop)

    def relay(self):
        with mock.patch.object(module.SubscriptionRelay, 'verify_subscription'):
            relay = module.SubscriptionRelay(self.temp.name, 'anthropic/fixture-model', max_requests=1)
        self.addCleanup(relay.close)
        return relay

    def request(self, relay, model='anthropic/fixture-model'):
        body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': 'private-request'}]}).encode()
        request = urllib.request.Request('http://127.0.0.1:' + str(relay.server.server_port) + '/v1/chat/completions',
            body, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer do-not-forward-native-secret'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
            return response.read()

    def test_actual_http_path_preserves_bytes_and_redacts_observations(self):
        relay = self.relay()
        self.assertEqual(self.request(relay), self.payload)
        self.assertEqual(self.seen[0][1], 'Bearer local-proxy-placeholder')
        log = relay.log.read_text()
        for private in ('private-request', 'private-response', 'do-not-forward-native-secret', 'Authorization'):
            self.assertNotIn(private, log)
        self.assertEqual(json.loads(log)['responseModels'], ['upstream-response-model'])
        self.assertEqual(relay.forwarded, 1)

    def test_wrong_model_and_exhausted_budget_never_reach_upstream(self):
        relay = self.relay()
        with self.assertRaises(urllib.error.HTTPError) as wrong:
            self.request(relay, 'openrouter/paid-fixture')
        self.assertEqual(wrong.exception.code, 400)
        wrong.exception.close()
        self.assertEqual(self.seen, [])
        self.request(relay)
        with self.assertRaises(urllib.error.HTTPError) as exhausted:
            self.request(relay)
        self.assertEqual(exhausted.exception.code, 429)
        exhausted.exception.close()
        self.assertEqual(len(self.seen), 1)

    def test_non_oauth_mode_refuses_before_opening_catalog_or_listener(self):
        with mock.patch.object(module.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='forward\n')), \
                mock.patch.object(module.urllib.request.OpenerDirector, 'open') as request, \
                mock.patch.object(module, 'ThreadingHTTPServer') as server:
            with self.assertRaisesRegex(ValueError, 'OAuth'):
                module.SubscriptionRelay(self.temp.name, 'anthropic/fixture-model')
        request.assert_not_called(); server.assert_not_called()
