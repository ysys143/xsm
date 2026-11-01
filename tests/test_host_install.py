"""Native host install ownership, CAS races and complete immutable assets."""
import json
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
        for part in ("xsm", "hooks", "skills", "bin", ".claude-plugin", ".codex-plugin", "clients", "integrations", "docs/protocol"):
            shutil.copytree(Path(REPO, part), self.source / part, ignore=shutil.ignore_patterns("__pycache__"))
        (self.source / "scripts").mkdir()
        for script in ("conform-host-protocol.py", "check-protocol-schema.py"):
            shutil.copy2(Path(REPO, "scripts", script), self.source / "scripts" / script)
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
        self.assertIn(b"nativeUi: true", loader.read_bytes())
        ui_file = Path(result["ui"]["file"])
        self.assertIn(result["ui"]["uri"], ui_file.read_text())
        self.assertTrue((Path(result["runtime_root"]) / "integrations/opencode/xsm.mjs").is_file())
        for filename in host_install.NATIVE_ASSETS["opencode"]:
            self.assertTrue((Path(result["runtime_root"]) / filename).is_file(), filename)
        self.assertFalse(host_install.apply("opencode", str(profile))["changed"])
        original = loader.read_bytes()
        loader.write_bytes(original + b"// user edit\n")
        with self.assertRaises(install.InstallConflictError):
            host_install.remove("opencode", str(profile))
        loader.write_bytes(original)
        host_install.remove("opencode", str(profile))
        self.assertFalse(loader.exists())
        self.assertFalse(ui_file.exists())
        self.assertEqual(settings.read_text(), '{"user":"retain"}')
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)

    def test_missing_native_ui_module_refuses_install_before_creating_a_profile(self):
        from xsm import host_install
        (self.source / "integrations/opencode/ui-channel.mjs").unlink()
        profile = Path(self.user_home, "missing-opencode")
        with self.assertRaisesRegex(ValueError, "lacks native host assets"):
            host_install.apply("opencode", str(profile))
        self.assertFalse(profile.exists())

    def test_invalid_ui_config_refuses_before_writing_a_backend_loader(self):
        from xsm import host_install, install
        profile = Path(self.user_home, "opencode-invalid")
        profile.mkdir()
        config = profile / "tui.jsonc"
        config.write_text('{"plugin":true}')
        with self.assertRaises(install.InstallConflictError):
            host_install.apply("opencode", str(profile))
        self.assertEqual(config.read_text(), '{"plugin":true}')
        self.assertFalse((profile / "plugins").exists())

    def test_user_edited_ui_snapshot_reference_is_kept_without_adopting_it(self):
        from xsm import host_install, install
        profile = Path(self.user_home, "opencode-manual")
        first = host_install.apply("opencode", str(profile))
        with (self.source / "xsm/paths.py").open("a") as stream:
            stream.write("\n# newer UI snapshot\n")
        host_install.apply("opencode", str(profile))
        config = Path(first["ui"]["file"])
        config.write_text('{"plugin":[' + json.dumps(first["ui"]["uri"]) + ']}')
        with self.assertRaises(install.InstallConflictError):
            host_install.apply("opencode", str(profile))
        self.assertIn(Path(first["runtime_root"]).name, install._configured_for())

    def test_ui_upgrade_recovery_keeps_the_actual_old_config_snapshot(self):
        from xsm import host_install, host_ui_config, install
        profile = Path(self.user_home, "opencode-recovery")
        first = host_install.apply("opencode", str(profile))
        original = Path(first["ui"]["file"]).read_bytes()
        for number in (1, 2):
            with (self.source / "xsm/paths.py").open("a") as stream:
                stream.write("\n# UI upgrade fixture %d\n" % number)
            with mock.patch.object(host_ui_config, "commit", side_effect=OSError("UI edit interrupted")):
                with self.assertRaises(OSError):
                    host_install.apply("opencode", str(profile))
            record = host_install.read_record("opencode", str(profile))
            self.assertEqual(record["phase"], "prepared")
            self.assertEqual(record["ui"]["previous_root"], first["runtime_root"])
            self.assertIn(Path(first["runtime_root"]).name, install._configured_for())
            self.assertEqual(Path(first["ui"]["file"]).read_bytes(), original)
        final = host_install.apply("opencode", str(profile))
        self.assertIn(final["runtime_root"], host_install.configured_roots())
        self.assertEqual(host_install.read_record("opencode", str(profile))["ui"]["phase"], "installed")

    def test_late_ui_edit_is_preserved_and_retry_owns_only_its_new_entry(self):
        from xsm import host_install, install
        profile = Path(self.user_home, "opencode-late")
        save = host_install.save_record
        def edit(record):
            save(record)
            if record["phase"] == "prepared":
                Path(record["ui"]["file"]).write_text('{"theme":"late-user"}')
        with mock.patch.object(host_install, "save_record", side_effect=edit):
            with self.assertRaises(install.InstallConflictError):
                host_install.apply("opencode", str(profile))
        config = profile / "tui.json"
        self.assertEqual(config.read_text(), '{"theme":"late-user"}')
        host_install.apply("opencode", str(profile))
        self.assertNotIn("late-user", str(host_install.read_record("opencode", str(profile))))
        host_install.remove("opencode", str(profile))
        self.assertEqual(config.read_text(), '{"theme":"late-user"}')

    def test_remove_recovers_after_ui_edit_before_backend_removal(self):
        from xsm import host_install, host_ui_config
        profile = Path(self.user_home, "opencode-remove")
        first = host_install.apply("opencode", str(profile))
        commit = host_ui_config.commit
        def interrupt(*args):
            commit(*args)
            raise OSError("stopped after UI removal")
        with mock.patch.object(host_ui_config, "commit", side_effect=interrupt):
            with self.assertRaises(OSError):
                host_install.remove("opencode", str(profile))
        self.assertFalse(Path(first["ui"]["file"]).exists())
        self.assertTrue(Path(first["file"]).exists())
        host_install.remove("opencode", str(profile))
        self.assertFalse(Path(first["file"]).exists())

    def test_removing_a_prepared_old_loader_and_manual_rollback_preservation(self):
        from xsm import host_install, install
        first = host_install.apply("pi", str(self.home))
        original = self.loader.read_bytes()
        with (self.source / "xsm/paths.py").open("a") as stream:
            stream.write("\n# second snapshot\n")
        save = host_install.save_record
        def interrupt(record):
            save(record)
            raise OSError("stopped after journal")
        with mock.patch.object(host_install, "save_record", side_effect=interrupt):
            with self.assertRaises(OSError):
                host_install.apply("pi", str(self.home))
        self.assertEqual(self.loader.read_bytes(), original)
        self.assertIn(Path(first["runtime_root"]).name, install._configured_for())
        with mock.patch.object(host_install, "save_record", side_effect=interrupt):
            with self.assertRaises(OSError):
                host_install.remove("pi", str(self.home))
        host_install.remove("pi", str(self.home))
        second = host_install.apply("pi", str(self.home))
        self.loader.write_bytes(original)
        with self.assertRaises(install.InstallConflictError):
            host_install.apply("pi", str(self.home))
        self.assertIn(Path(first["runtime_root"]).name, install._configured_for())
        self.assertNotEqual(first["runtime_root"], second["runtime_root"])

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
        for filename in ("clients/python/__init__.py", "clients/python/xsm_host.py", "integrations/hermes/xsm.py",
                         "integrations/openclaw/xsm.mjs", "integrations/openclaw/tools.mjs",
                         "integrations/openclaw/context-queue.mjs",
                         "integrations/openclaw/openclaw.plugin.json"):
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

    def test_hermes_install_update_remove_preserves_settings_and_other_files(self):
        from xsm import host_install
        profile = Path(self.user_home, "hermes")
        profile.mkdir()
        settings = profile / "config.yaml"
        settings.write_text("plugins:\n  enabled: []\n")
        settings.chmod(0o640)
        first = host_install.apply("hermes", str(profile))
        folder = profile / "plugins/xsm"
        extra = folder / "notes.txt"
        extra.write_text("user")
        self.assertEqual(first["activation"], "operator-opt-in")
        self.assertIn(first["runtime_root"], host_install.configured_roots())
        self.assertFalse(host_install.apply("hermes", str(profile))["changed"])
        self.assertIn(first["runtime_root"], (folder / "__init__.py").read_text())
        self.assertTrue((folder / "plugin.yaml").read_text().startswith("# xsm managed Hermes"))
        host_install.remove("hermes", str(profile))
        self.assertFalse((folder / "__init__.py").exists())
        self.assertFalse((folder / "plugin.yaml").exists())
        self.assertEqual(extra.read_text(), "user")
        self.assertEqual(settings.read_text(), "plugins:\n  enabled: []\n")
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)

    def test_hermes_edited_manifest_refuses_all_mutation(self):
        from xsm import host_install, install
        profile = Path(self.user_home, "hermes-edited")
        host_install.apply("hermes", str(profile))
        folder = profile / "plugins/xsm"
        original = (folder / "__init__.py").read_bytes()
        manifest = folder / "plugin.yaml"
        manifest.write_text(manifest.read_text() + "\n# user edit\n")
        for action in (host_install.apply, host_install.remove):
            with self.assertRaisesRegex(install.InstallConflictError, "edited Hermes"):
                action("hermes", str(profile))
            self.assertEqual((folder / "__init__.py").read_bytes(), original)
            self.assertIn("user edit", manifest.read_text())

    def test_hermes_interrupted_initial_install_can_be_recovered(self):
        from xsm import host_install, hermes_install
        profile = Path(self.user_home, "hermes-recovery")
        original = hermes_install.replace
        def interrupt(fd, guard, name, *args):
            if name == "plugin.yaml":
                raise OSError("interrupted second file")
            return original(fd, guard, name, *args)
        with mock.patch.object(hermes_install, "replace", side_effect=interrupt):
            with self.assertRaisesRegex(OSError, "interrupted"):
                host_install.apply("hermes", str(profile))
        self.assertEqual(host_install.inspect("hermes", str(profile))["status"], "partial")
        self.assertEqual(host_install.read_record("hermes", str(profile))["phase"], "prepared")
        final = host_install.apply("hermes", str(profile))
        self.assertEqual(final["status"], "installed")
        self.assertEqual(host_install.read_record("hermes", str(profile))["phase"], "installed")

    def test_hermes_symlink_plugin_directory_is_preserved(self):
        from xsm import host_install
        profile = Path(self.user_home, "hermes-link")
        (profile / "plugins").mkdir(parents=True)
        outside = Path(self.user_home, "outside")
        outside.mkdir()
        (profile / "plugins/xsm").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            host_install.apply("hermes", str(profile))
        self.assertEqual(list(outside.iterdir()), [])

    def test_hermes_dry_run_does_not_create_native_profile(self):
        from xsm import host_install
        profile = Path(self.user_home, "hermes-dry")
        result = host_install.apply("hermes", str(profile), dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(profile.exists())

    def test_hermes_prepared_upgrade_keeps_old_loader_snapshot_until_recovery(self):
        from xsm import host_install, hermes_install
        profile = Path(self.user_home, "hermes-upgrade")
        first = host_install.apply("hermes", str(profile))
        with (self.source / "xsm/paths.py").open("a") as stream:
            stream.write("\n# Hermes update fixture\n")
        with mock.patch.object(hermes_install, "replace", side_effect=OSError("before loader swap")):
            with self.assertRaises(OSError):
                host_install.apply("hermes", str(profile))
        pending = host_install.read_record("hermes", str(profile))
        self.assertNotEqual(first["runtime_root"], pending["root"])
        self.assertIn(first["runtime_root"], host_install.configured_roots())
        self.assertIn(pending["root"], host_install.configured_roots())
        updated = host_install.apply("hermes", str(profile))
        self.assertEqual(updated["runtime_root"], pending["root"])
        self.assertNotIn(first["runtime_root"], host_install.configured_roots())

    def test_hermes_symlink_plugins_parent_is_preserved(self):
        from xsm import host_install
        profile = Path(self.user_home, "hermes-parent-link")
        profile.mkdir()
        outside = Path(self.user_home, "outside-plugins")
        outside.mkdir()
        (profile / "plugins").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            host_install.apply("hermes", str(profile))
        self.assertEqual(list(outside.iterdir()), [])


    def test_installed_snapshot_exports_its_public_protocol_contract_without_checkout(self):
        import hashlib
        import subprocess
        import sys
        from xsm import host_install, install
        result = host_install.apply("pi", str(self.home))
        root = Path(result["runtime_root"])
        self.assertTrue((root / "docs/protocol/request.schema.json").is_file())
        self.assertTrue((root / "scripts/conform-host-protocol.py").is_file())
        self.assertTrue((root / "scripts/check-protocol-schema.py").is_file())
        shutil.rmtree(self.source)
        env = dict(PATH=os.environ.get("PATH", os.defpath), HOME=self.user_home,
                   XSM_HOME=self.tmp, PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run([sys.executable, "-B", "-c", install.BOOT, str(root),
                                  "protocol", "describe"], cwd=self.user_home, env=env,
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        bundle = json.loads(process.stdout)
        self.assertEqual(bundle["protocolVersion"], "1")
        self.assertTrue(bundle["experimental"])
        self.assertEqual(len(bundle["methods"]), 11)
        self.assertEqual(len(bundle["operations"]), 21)
        for name, artifact in bundle["artifacts"].items():
            content = (root / name).read_bytes()
            self.assertEqual(artifact["text"].encode(), content)
            self.assertEqual(artifact["sha256"], hashlib.sha256(content).hexdigest())
        self.assertIn("docs/protocol/output.schema.json", bundle["artifacts"])
        self.assertIn("scripts/conform-host-protocol.py", bundle["artifacts"])

        report = Path(self.tmp, "snapshot-conformance.json")
        checked = subprocess.run([sys.executable, "-B", str(root / "scripts/conform-host-protocol.py"),
            "--output", str(report), "--command", sys.executable, "-B", "-c", install.BOOT, str(root),
            "protocol", "serve", "--stdio"], cwd=self.user_home, env=env,
            capture_output=True, text=True, timeout=20)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(len(json.loads(report.read_text())["checks"]), 16)

    def test_contract_export_refuses_partial_artifact_set(self):
        from xsm import protocol_contract
        (self.source / "docs/protocol/output.schema.json").unlink()
        with self.assertRaisesRegex(ValueError, "public protocol artifacts missing"):
            protocol_contract.bundle(self.source)

    def test_contract_export_does_not_follow_an_artifact_symlink(self):
        from xsm import protocol_contract
        outside = Path(self.tmp, "not-a-public-artifact")
        outside.write_text("must-not-export")
        artifact = self.source / "docs/protocol/output.schema.json"
        artifact.unlink()
        artifact.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "artifact symlink or outside installation"):
            protocol_contract.bundle(self.source)

    def test_protocol_describe_does_not_initialize_state_or_home(self):
        import subprocess
        import sys
        state = Path(self.tmp, 'uncreated-state')
        home = Path(self.tmp, 'uncreated-home')
        env = dict(PATH=os.environ.get('PATH', os.defpath), HOME=str(home), XSM_HOME=str(state),
                   PYTHONPATH=REPO, PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-B', '-m', 'xsm', 'protocol', 'describe'],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['protocolVersion'], '1')
        self.assertFalse(state.exists())
        self.assertFalse(home.exists())
