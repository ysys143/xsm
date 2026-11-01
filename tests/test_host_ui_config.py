"""Native TUI URI ownership and JSONC preservation, without native credentials."""
import json
import os
from pathlib import Path
import stat
from unittest import mock

from tests.test_xsm import TempState


class JsoncEditTest(TempState):
    def test_comments_trailing_commas_strings_and_unicode(self):
        from xsm.jsonc_edit import Document
        text = '\ufeff{/* lead */"url":"https://x/* literal */", "s":",]", // comment\r\n"plugin":["사용자",],}'
        document = Document(text)
        self.assertEqual(document.value, {"url": "https://x/* literal */", "s": ",]", "plugin": ["사용자"]})
        after, fragment = document.insert("file:///xsm/tui.mjs")
        self.assertEqual(after.replace(fragment, "", 1), text)
        self.assertEqual(Document(after).value["plugin"], ["사용자", "file:///xsm/tui.mjs"])
        removed = Document(after).remove(1)
        self.assertEqual(Document(removed).value, document.value)
        self.assertIn("/* lead */", removed)
        self.assertIn("// comment\r\n", removed)

    def test_insert_remove_for_empty_and_populated_objects_and_arrays(self):
        from xsm.jsonc_edit import Document
        for text in ('{}', '{/*comment*/}', '{"theme":"mine"}', '{"plugin":[]}',
                     '{"plugin":[/*comment*/]}', '{"plugin":["a"]}', '{"plugin":["a",]}'):
            before = Document(text)
            after, fragment = before.insert("uri")
            self.assertEqual(after.replace(fragment, "", 1), text)
            self.assertEqual(Document(after).value["plugin"][-1], "uri")
            removed = Document(after).remove(len(before.plugins()))
            self.assertEqual(Document(removed).value.get("plugin", []), before.value.get("plugin", []))

    def test_array_removal_keeps_comments_and_other_plugin_options(self):
        from xsm.jsonc_edit import Document
        for index in (0, 1, 2):
            text = '{"plugin":["a", /* retain */ ["b",{"option":true}], "c",]}'
            document = Document(text)
            expected = document.value["plugin"][:]
            expected.pop(index)
            after = document.remove(index)
            self.assertEqual(Document(after).value["plugin"], expected)
            self.assertIn("/* retain */", after)

    def test_invalid_or_ambiguous_config_is_refused(self):
        from xsm.jsonc_edit import Document
        for text in ('{"plugin":[],"plugin":[]}', '{/*broken', '[]', '{"plugin":true}', '{"plugin":[false]}', '{"x":NaN}'):
            with self.assertRaises(ValueError, msg=text):
                Document(text).plugins()


class HostUiConfigTest(TempState):
    def setUp(self):
        super().setUp()
        self.home = Path(self.user_home, "opencode")
        self.home.mkdir()
        self.root = Path(self.tmp, "runtime", "a")
        self.owned = None

    def apply(self, root=None):
        from xsm import host_ui_config as ui, host_install as host
        state = ui.inspect(str(self.home), self.owned)
        plan = ui.prepare(state, self.owned, str(root or self.root))
        hfd, pfd = host._open_dirs(str(self.home), ".", False)
        try:
            ui.commit(plan, hfd)
        finally:
            os.close(pfd)
            os.close(hfd)
        self.owned = dict(plan["record"], phase="installed", previous_root=None, previous_uri=None)
        return plan

    def remove(self):
        from xsm import host_ui_config as ui, host_install as host
        plan = ui.prepare(ui.inspect(str(self.home), self.owned), self.owned)
        hfd, pfd = host._open_dirs(str(self.home), ".", False)
        try:
            ui.commit(plan, hfd)
        finally:
            os.close(pfd)
            os.close(hfd)
        return plan

    def test_created_config_is_idempotent_and_removed_only_if_still_owned(self):
        self.apply()
        config = self.home / "tui.json"
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
        self.assertFalse(self.apply()["changed"])
        self.remove()
        self.assertFalse(config.exists())

    def test_existing_jsonc_restores_original_bytes_and_mode_across_updates(self):
        config = self.home / "tui.jsonc"
        original = b'{// keep\r\n "theme":"mine", "plugin":["other", /*keep*/],}\r\n'
        config.write_bytes(original)
        config.chmod(0o640)
        self.apply()
        self.apply(Path(self.tmp, "runtime", "b"))
        self.remove()
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o640)

    def test_new_user_settings_and_plugins_survive_uninstall_and_upgrade(self):
        self.apply()
        config = self.home / "tui.json"
        value = json.loads(config.read_text())
        value.update(theme="user-added")
        value["plugin"].append(["user-plugin", {"option": True}])
        config.write_text(json.dumps(value))
        self.apply(Path(self.tmp, "runtime", "b"))
        self.remove()
        self.assertEqual(json.loads(config.read_text()), {"theme": "user-added", "plugin": [["user-plugin", {"option": True}]]})

    def test_both_config_files_keep_unrelated_data(self):
        first = self.home / "tui.json"
        first.write_text('{"plugin":["json-user"]}')
        second = self.home / "tui.jsonc"
        second.write_text('{"plugin":["jsonc-user"]}')
        original = first.read_bytes()
        self.apply()
        self.assertEqual(Path(self.owned["file"]), second)
        self.remove()
        self.assertEqual(first.read_bytes(), original)
        self.assertEqual(second.read_text(), '{"plugin":["jsonc-user"]}')

    def test_foreign_xsm_entry_and_modified_options_are_preserved(self):
        from xsm import host_ui_config as ui, install
        config = self.home / "tui.json"
        config.write_text(json.dumps({"plugin": [self.root.joinpath("integrations/opencode/tui.mjs").as_uri()]}))
        with self.assertRaises(install.InstallConflictError):
            ui.inspect(str(self.home))
        config.unlink()
        self.apply()
        config.write_text(json.dumps({"plugin": [[self.owned["uri"], {"user": True}]]}))
        with self.assertRaises(install.InstallConflictError):
            self.remove()
        self.assertTrue(config.exists())

    def test_symlink_late_edit_and_profile_replacement_are_not_overwritten(self):
        from xsm import host_ui_config as ui, host_install as host, install
        config = self.home / "tui.json"
        foreign = Path(self.tmp, "foreign.json")
        foreign.write_text('{"user":true}')
        config.symlink_to(foreign)
        with self.assertRaises(install.InstallConflictError):
            ui.inspect(str(self.home))
        config.unlink()
        plan = ui.prepare(ui.inspect(str(self.home)), None, str(self.root))
        config.write_text('{"late":"user"}')
        hfd = os.open(str(self.home), os.O_RDONLY | host.DIRECTORY)
        try:
            with self.assertRaises(install.InstallConflictError):
                ui.commit(plan, hfd)
        finally:
            os.close(hfd)
        self.assertEqual(config.read_text(), '{"late":"user"}')
        plan = ui.prepare(ui.inspect(str(self.home)), None, str(self.root))
        self.home.rename(self.home.with_name("old-opencode"))
        self.home.mkdir()
        hfd = os.open(str(self.home), os.O_RDONLY | host.DIRECTORY)
        try:
            with self.assertRaises(install.InstallConflictError):
                ui.commit(plan, hfd)
        finally:
            os.close(hfd)
        self.assertEqual(foreign.read_text(), '{"user":true}')

    def test_existing_ui_file_changed_after_plan_is_not_replaced(self):
        from xsm import host_ui_config as ui, host_install as host, install
        config = self.home / "tui.json"
        config.write_text('{"theme":"before"}')
        plan = ui.prepare(ui.inspect(str(self.home)), None, str(self.root))
        config.write_text('{"theme":"after-user-edit"}')
        hfd = os.open(str(self.home), os.O_RDONLY | host.DIRECTORY)
        try:
            with self.assertRaises(install.InstallConflictError):
                ui.commit(plan, hfd)
        finally:
            os.close(hfd)
        self.assertEqual(config.read_text(), '{"theme":"after-user-edit"}')

    def test_prepared_journal_recovers_before_or_after_config_commit(self):
        from xsm import host_ui_config as ui
        self.apply()
        next_root = Path(self.tmp, "runtime", "b")
        plan = ui.prepare(ui.inspect(str(self.home), self.owned), self.owned, str(next_root))
        self.owned = plan["record"]  # crash before the prepared edit was applied
        self.apply(next_root)
        plan = ui.prepare(ui.inspect(str(self.home), self.owned), self.owned, str(self.root))
        self.owned = plan["record"]
        (self.home / "tui.json").write_bytes(plan["after"])  # crash after edit, before final journal
        self.assertFalse(self.apply(self.root)["changed"])
        self.remove()
        self.assertFalse((self.home / "tui.json").exists())
