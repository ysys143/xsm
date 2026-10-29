"""Published agent instructions and tool installation must follow the service."""
from pathlib import Path
import unittest


class MessagingInstructionsTest(unittest.TestCase):
    def test_generated_guide_and_mcp_semantics_have_one_source(self):
        from xsm import instructions, mcp
        root = Path(instructions.__file__).resolve().parent.parent
        guide = root / "skills/xsm/references/messaging.md"
        self.assertEqual(guide.read_text(), instructions.MESSAGING_GUIDE)
        ask = next(t for t in mcp.TOOLS if t["name"] == "xsm_ask")
        self.assertEqual(ask["description"], instructions.MESSAGING_GUIDE)
        self.assertIn("MCP first", instructions.MESSAGING_GUIDE)

    def test_new_mcp_and_cli_interfaces_are_in_the_appropriate_installer_catalog(self):
        from xsm import install, mcp
        names = {t["name"] for t in mcp.TOOLS}
        self.assertTrue({"xsm_ask", "xsm_connect", "xsm_question_status", "xsm_discover",
                         "xsm_publish"} <= names)
        self.assertTrue({"xsm_connect", "xsm_ask", "xsm_question_status", "xsm_discover"} <= set(install.MESSAGING_TOOLS))
        self.assertTrue({"xsm_publish"} <= set(install.FORM_TOOLS))
        self.assertTrue({"publish"} <= set(install.ASKING_COMMANDS))

    def test_connect_handshake_does_not_bypass_allow_messaging_false(self):
        from unittest import mock
        from xsm import install
        self.assertNotIn("xsm_connect", install.FORM_TOOLS)
        self.assertNotIn("connect", install.ASKING_COMMANDS)
        with mock.patch.object(install.policy, "get", return_value=False):
            rules = install.wanted_rules("/fixture/home")
        self.assertFalse(any("xsm_connect" in rule or "xsm connect:" in rule for rule in rules))
