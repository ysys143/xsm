"""The synchronous native catalog must match the common protocol, without drift."""
import json
from pathlib import Path
import unittest

from xsm.operation_schema import TOOLS


class OpenClawSchemaTest(unittest.TestCase):
    def test_native_catalog_and_manifest_match_common_operations(self):
        root = Path(__file__).resolve().parents[1] / 'integrations/openclaw'
        text = (root / 'tools.mjs').read_text()
        catalog = json.loads(text.split('export default ', 1)[1].removesuffix(';\n'))
        self.assertEqual(catalog, TOOLS)
        manifest = json.loads((root / 'openclaw.plugin.json').read_text())
        self.assertEqual(manifest['contracts']['tools'], [tool['name'] for tool in TOOLS])
        hermes = json.loads((root.parent / 'hermes/plugin.yaml').read_text())
        self.assertEqual(hermes['provides_tools'], [tool['name'] for tool in TOOLS])
