"""Native host install ownership, CAS races and complete immutable assets."""
import os
from pathlib import Path
import shutil
import stat
from unittest import mock

from tests.test_xsm import TempState, REPO


class HostInstallTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import install
        self.source = Path(self.tmp, "checkout")
        for part in ("xsm", "hooks", "skills", "bin", ".claude-plugin", ".codex-plugin", "clients", "integrations"):
            shutil.copytree(Path(REPO, part), self.source / part, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(Path(REPO, "LICENSE"), self.source / "LICENSE")
        patch = mock.patch.object(install, "REPO", str(self.source))
        patch.start()
        self.addCleanup(patch.stop)
        self.home = Path(self.user_home, "pi")
        self.loader = self.home / "extensions/xsm.js"

    def test_opencode_loader_uses_native_sdk_and_preserves_profile_configuration(self):
        from xsm import host_install, install
        profile = Path(self.user_home, "opencode")
        profile.mkdir()
        settings = profile / "opencode.json"
        settings.write_text('{"user":"retain"}')
        settings.chmod(0o640)
        result = host_install.apply("opencode", str(profile))
        loader = profile / "plugins/xsm.js"
        self.assertEqual(Path(result["file"]).resolve(), loader.resolve())
        self.assertIn(b"import { tool } from '@opencode-ai/plugin'", loader.read_bytes())
        self.assertIn(b"schema: tool.schema", loader.read_bytes())
        self.assertTrue((Path(result["runtime_root"]) / "integrations/opencode/xsm.mjs").is_file())
        self.assertFalse(host_install.apply("opencode", str(profile))["changed"])
        original = loader.read_bytes()
        loader.write_bytes(original + b"// user edit\n")
        with self.assertRaises(install.InstallConflictError):
            host_install.remove("opencode", str(profile))
        loader.write_bytes(original)
        host_install.remove("opencode", str(profile))
        self.assertFalse(loader.exists())
        self.assertEqual(settings.read_text(), '{"user":"retain"}')
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)

    def test_clean_install_idempotent_and_complete_assets_leave_settings_untouched(self):
        from xsm import host_install
        self.home.mkdir()
        settings = self.home / "settings.json"
        settings.write_text('{"user":"retain"}')
        settings.chmod(0o640)
        first = host_install.apply("pi", str(self.home))
        root = Path(first["runtime_root"])
        for filename in host_install.SHARED + ("integrations/pi/xsm.mjs",):
            self.assertTrue((root / filename).is_file(), filename)
        original = self.loader.read_bytes()
        self.assertIn(root.as_uri().encode(), original)
        self.assertFalse(host_install.apply("pi", str(self.home))["changed"])
        self.assertEqual(self.loader.read_bytes(), original)
        self.assertEqual(settings.read_text(), '{"user":"retain"}')
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)

    def test_direct_dry_run_creates_no_native_profile_or_ownership_record(self):
        from xsm import host_install
        result = host_install.apply("pi", str(self.home), dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.home.exists())
        self.assertFalse(Path(host_install.record_path("pi", str(self.home))).exists())

    def test_foreign_and_edited_loader_are_preserved(self):
        from xsm import host_install, install
        self.loader.parent.mkdir(parents=True)
        self.loader.write_text("user-owned extension")
        with self.assertRaises(install.InstallConflictError):
            host_install.apply("pi", str(self.home))
        self.assertEqual(self.loader.read_text(), "user-owned extension")
        self.loader.unlink()
        host_install.apply("pi", str(self.home))
        self.loader.write_text("user edit after install")
        for action in (host_install.apply, host_install.remove):
            with self.assertRaises(install.InstallConflictError):
                action("pi", str(self.home))
        self.assertEqual(self.loader.read_text(), "user edit after install")

    def test_symlink_file_and_parent_are_never_followed(self):
        from xsm import host_install
        foreign = Path(self.tmp, "foreign")
        foreign.mkdir()
        actual = foreign / "xsm.js"
        actual.write_text("foreign")
        self.home.mkdir()
        (self.home / "extensions").symlink_to(foreign, target_is_directory=True)
        with self.assertRaises(OSError):
            host_install.apply("pi", str(self.home))
        (self.home / "extensions").unlink()
        self.loader.parent.mkdir()
        self.loader.symlink_to(actual)
        with self.assertRaises(ValueError):
            host_install.apply("pi", str(self.home))
        self.assertEqual(actual.read_text(), "foreign")

    def test_update_preserves_user_mode_and_old_configured_snapshot(self):
        from xsm import host_install, install
        first = host_install.apply("pi", str(self.home))
        self.loader.chmod(0o640)
        with (self.source / "xsm/paths.py").open("a") as stream:
            stream.write("\n# next private test snapshot\n")
        # Another install can advance current while this profile still names old.
        second = install.make_snapshot()
        self.assertNotEqual(second["path"], first["runtime_root"])
        self.assertIn(Path(first["runtime_root"]).name, install._configured_for())
        changed = host_install.apply("pi", str(self.home))
        self.assertTrue(changed["changed"])
        self.assertEqual(stat.S_IMODE(self.loader.stat().st_mode), 0o640)
        self.assertIn(Path(changed["runtime_root"]).as_uri(), self.loader.read_text())

    def test_user_edit_after_prepare_is_not_overwritten(self):
        from xsm import host_install, install
        save = host_install.save_record
        def edit(record):
            save(record)
            if record["phase"] == "prepared":
                self.loader.write_text("late user edit")
        with mock.patch.object(host_install, "save_record", side_effect=edit):
            with self.assertRaises(install.InstallConflictError):
                host_install.apply("pi", str(self.home))
        self.assertEqual(self.loader.read_text(), "late user edit")

    def test_directory_replacement_after_prepare_preserves_foreign_directory(self):
        from xsm import host_install, install
        foreign = Path(self.tmp, "foreign")
        foreign.mkdir()
        save = host_install.save_record
        def replace(record):
            save(record)
            if record["phase"] == "prepared":
                self.loader.parent.rename(self.home / "original-extensions")
                self.loader.parent.symlink_to(foreign, target_is_directory=True)
        with mock.patch.object(host_install, "save_record", side_effect=replace):
            with self.assertRaises(install.InstallConflictError):
                host_install.apply("pi", str(self.home))
        self.assertEqual(list(foreign.iterdir()), [])

    def test_interrupted_final_ownership_save_recovers_the_exact_loader(self):
        from xsm import host_install
        save = host_install.save_record
        def interrupt(record):
            if record["phase"] == "installed":
                raise OSError("ownership completion interrupted")
            save(record)
        with mock.patch.object(host_install, "save_record", side_effect=interrupt):
            with self.assertRaises(OSError):
                host_install.apply("pi", str(self.home))
        written = self.loader.read_bytes()
        self.assertEqual(host_install.read_record("pi", str(self.home))["phase"], "prepared")
        self.assertFalse(host_install.apply("pi", str(self.home))["changed"])
        self.assertEqual(self.loader.read_bytes(), written)

    def test_uninstall_removes_only_owned_loader_and_keeps_foreign_extension(self):
        from xsm import host_install
        host_install.apply("pi", str(self.home))
        other = self.loader.parent / "user.mjs"
        other.write_text("retained")
        removed = host_install.remove("pi", str(self.home))
        self.assertTrue(removed["changed"])
        self.assertFalse(self.loader.exists())
        self.assertEqual(other.read_text(), "retained")
        self.assertEqual(host_install.read_record("pi", str(self.home))["phase"], "removed")

    def test_snapshot_id_detection_includes_bare_protocol_launcher_root(self):
        from xsm import install
        root = install.runtime_dir("a" * 12)
        self.assertEqual(install._snapshot_ids('python -c boot "' + root + '" protocol serve --stdio'), {"a" * 12})
        self.assertEqual(install._snapshot_ids(root + "b/file.py"), set())

    def test_uninstall_preserves_user_edit_after_remove_intent(self):
        from xsm import host_install, install
        host_install.apply("pi", str(self.home))
        save = host_install.save_record
        def edit(record):
            save(record)
            if record["phase"] == "removing":
                self.loader.write_text("edited during removal")
        with mock.patch.object(host_install, "save_record", side_effect=edit):
            with self.assertRaises(install.InstallConflictError):
                host_install.remove("pi", str(self.home))
        self.assertEqual(self.loader.read_text(), "edited during removal")

    def test_corrupt_ownership_blocks_mutation_and_preserves_snapshots(self):
        from xsm import host_install, install
        old = host_install.apply("pi", str(self.home))
        content = self.loader.read_bytes()
        with (self.source / "xsm/paths.py").open("a") as stream:
            stream.write("\n# second private snapshot\n")
        current = install.make_snapshot()
        Path(host_install.record_path("pi", str(self.home))).write_text("{")
        for action in (host_install.apply, host_install.remove):
            with self.assertRaises(ValueError):
                action("pi", str(self.home))
        self.assertEqual(self.loader.read_bytes(), content)
        retained = install._configured_for()
        self.assertIn(Path(old["runtime_root"]).name, retained)
        self.assertIn(current["id"], retained)
