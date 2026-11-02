"""Actual SDK loader subprocess with an explicit package fixture; no native proof."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from integrations.openclaw.worker_session import NativeSessionError
from integrations.openclaw.worker_transport import NativeRpc


class OpenClawWorkerTransportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='xsm-openclaw-rpc-fixture-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.package = root / 'package.json'
        self.package.write_text(json.dumps(dict(name='openclaw', version='2026.10.9', type='module',
            exports={'./plugin-sdk/gateway-runtime': './fixture.mjs'})))
        (root / 'openclaw.mjs').write_text('// Explicit fixture executable locator, not native OpenClaw.\n')
        (root / 'fixture.mjs').write_text('''
export async function callGatewayFromCli(method,options,params,extra) {
 if (params.fail) throw new Error('fixture credential must stay private');
 return {method,options,params,extra,privateHintPresent:'XSM_OWNED_CONTROL_FD' in process.env};
}
''')
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
        env.update(HOME=str(root), XSM_OWNED_CONTROL_FD='fixture-not-a-real-fd')
        node = shutil.which('node')
        self.assertIsNotNone(node)
        self.rpc = NativeRpc(node, str(root / 'openclaw.mjs'), cwd=str(root), env=env)

    def test_public_sdk_receives_backend_options_and_exact_request(self):
        result = self.rpc('sessions.resolve', dict(sessionId='exact-id', agentId='main'))
        self.assertEqual(result['params'], dict(sessionId='exact-id', agentId='main'))
        self.assertEqual(result['extra'], dict(mode='backend', clientName='gateway-client',
                                              progress=False, scopes=['operator.admin']))
        self.assertFalse(result['privateHintPresent'])

    def test_unknown_native_method_is_rejected_before_sdk_dispatch(self):
        with self.assertRaises(NativeSessionError):
            self.rpc('arbitrary-internal-method', {})

    def test_other_native_version_is_not_silently_adopted(self):
        package = json.loads(self.package.read_text())
        package['version'] = 'different'
        self.package.write_text(json.dumps(package))
        with self.assertRaises(NativeSessionError):
            self.rpc('health', {})

    def test_native_failure_does_not_export_error_contents_or_retry(self):
        with self.assertRaises(NativeSessionError) as error:
            self.rpc('health', dict(fail=True))
        self.assertNotIn('fixture credential', str(error.exception))
