"""P06 module preparation, not G06: G04/shared delivery integration is pending.

Explicit fixture quotas/retention only. No model process or external transfer.
"""
import base64
import copy
from dataclasses import asdict, replace
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest import mock

from tests import test_xsm


class FilesTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import files, paths
        self.f, self.paths = files, paths
        self.root = Path(self.tmp)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.sender = {"runtime": "codex", "home": str(self.root / "profile-a"),
                       "session_id": "sender", "cwd": str(self.workspace), "certainty": "certain"}
        self.receiver = {"runtime": "claude", "home": str(self.root / "profile-b"),
                         "session_id": "receiver", "cwd": str(self.artifacts), "certainty": "certain"}
        self.limits = files.Limits(file_bytes=1024, total_bytes=4096, max_files=8,
                                   quota_bytes=32768, retention_seconds=60, inline_bytes=8192)
        self.request, self.body = "request-original", "원래 질문\n검토해주세요."

    def prepare(self, items=None, **kwargs):
        return self.f.prepare_inline(self.sender, self.request, self.body,
            items if items is not None else [{"name": "review.txt", "text": "exact copy\n한글"}],
            limits=kwargs.pop("limits", self.limits), now=kwargs.pop("now", 100), **kwargs)

    def packet(self, value):
        return self.f.export_packet(self.sender, value["id"], request_id=self.request,
                                    body=self.body, now=101)

    def receive(self, packet, **kwargs):
        return self.f.receive(self.receiver, packet, request_id=kwargs.pop("request_id", self.request),
            body=kwargs.pop("body", self.body), limits=kwargs.pop("limits", self.limits),
            expected_reference=kwargs.pop("expected_reference", self.f.reference(packet["manifest"])),
            now=kwargs.pop("now", 102), **kwargs)

    def source(self, name="source.txt", data=b"original bytes"):
        path = self.artifacts / name
        path.write_bytes(data)
        return path

    def cli(self, sources, **kwargs):
        return self.f.prepare_cli(self.sender, self.request, self.body, sources,
                                 limits=kwargs.pop("limits", self.limits), now=kwargs.pop("now", 100), **kwargs)

    def bundles(self, kind):
        path = Path(self.paths.path(self.f.DIRECTORY, kind))
        return list(path.iterdir()) if path.exists() else []

    def resign(self, packet):
        value = packet["manifest"]
        value["sha256"] = hashlib.sha256(json.dumps({k: v for k, v in value.items() if k != "sha256"},
            sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return packet

    def test_limits_are_required_fixture_inputs_not_product_defaults(self):
        with self.assertRaises(TypeError):
            self.f.Limits()
        for updates in ({"file_bytes": 0}, {"max_files": True}, {"quota_bytes": -1},
                        {"retention_seconds": float("inf")}, {"retention_seconds": None}):
            with self.subTest(updates=updates), self.assertRaises(self.f.FileError):
                replace(self.limits, **updates)

    def test_product_limits_use_only_approved_values_and_shared_request_inline_limit(self):
        limits = self.f.product_limits()
        self.assertEqual((limits.file_bytes, limits.total_bytes, limits.max_files, limits.quota_bytes,
                          limits.retention_seconds), (1048576, 4194304, 16, 268435456, 604800))
        self.assertEqual(limits.inline_bytes, 4194304)
        for value in (1, self.f.JSON_BOUND, self.f.JSON_BOUND + 1, self.f.REQUEST_BYTES):
            self.assertEqual(self.f.product_limits(inline_bytes=value).inline_bytes, value)
        for invalid in (0, -1, True, self.f.REQUEST_BYTES + 1):
            with self.subTest(value=invalid), self.assertRaises(self.f.FileError):
                self.f.product_limits(inline_bytes=invalid)
        value = self.prepare(limits=limits)
        result = self.f.negotiate(self.packet(value), request_id=self.request, body=self.body,
                                 capability=None, limits=limits, fallback="inline")
        self.assertEqual(result["mode"], "inline")
        with self.assertRaises(self.f.FileError):
            self.f.negotiate(self.packet(value), request_id=self.request, body=self.body,
                             capability=None, limits=limits, fallback="inline", body_limit=10)

    def test_product_four_mib_bundle_uses_file_carrier_with_explicit_smaller_inline_fixture(self):
        limits = self.f.product_limits(inline_bytes=self.f.JSON_BOUND)  # Explicit test fixture, not a default.
        chunk = b"x" * limits.file_bytes
        value = self.prepare([{"name": "part%d.txt" % n, "data": chunk} for n in range(4)], limits=limits)
        packet = self.packet(value)
        self.assertEqual(value["size"], 4194304)
        files = self.f.negotiate(packet, request_id=self.request, body=self.body,
                                capability={"status": "observed", "version": 1}, limits=limits)
        self.assertEqual(files["body"], self.body)
        self.assertEqual(files["mode"], "files")
        with self.assertRaises(self.f.FileError) as error:
            self.f.negotiate(packet, request_id=self.request, body=self.body,
                             capability=None, limits=limits, fallback="inline")
        self.assertEqual(error.exception.code, "inline-too-large")

    def test_metadata_parser_bound_is_not_the_rendered_inline_body_cap(self):
        limits = self.f.product_limits()
        value = self.prepare([{"name": "a.txt", "data": b"x" * limits.file_bytes},
                              {"name": "b.txt", "data": b"y" * limits.file_bytes}], limits=limits)
        packet = self.packet(value)
        inline = self.f.negotiate(packet, request_id=self.request, body=self.body,
                                  capability=None, limits=limits, fallback="inline")
        size = len(inline["body"].encode())
        self.assertGreater(size, self.f.JSON_BOUND)
        self.assertLessEqual(size, limits.inline_bytes)
        with self.assertRaises(self.f.FileError):
            self.f.negotiate(packet, request_id=self.request, body=self.body, capability=None,
                             limits=limits, fallback="inline", body_limit=self.f.JSON_BOUND)

    def test_cli_inline_and_received_copy_have_same_bytes_and_request_binding(self):
        data = "사본 내용\n그대로".encode()
        cli = self.cli([str(self.source("review.txt", data))])
        inline = self.prepare([{"name": "review.txt", "data": data}])
        self.assertEqual(cli["files"][0]["sha256"], inline["files"][0]["sha256"])
        self.assertEqual(cli["binding"]["request_id"], self.request)
        self.assertEqual(cli["binding"]["body_sha256"], hashlib.sha256(self.body.encode()).hexdigest())
        self.assertEqual(cli["files"][0]["input_source"], "cli-os-read")
        self.assertEqual(inline["files"][0]["input_source"], "caller-inline")
        packet = self.packet(cli)
        self.assertNotIn(self.tmp, json.dumps(packet))
        received = self.receive(packet)
        self.assertEqual(received["status"], "files-stored")
        self.assertNotEqual(received["storage_id"], cli["id"])
        self.assertNotIn("delivered", received)
        self.assertEqual(self.f.read_copy(self.receiver, received["storage_id"], cli["files"][0]["id"], incoming=True), data)
        reference = self.f.reference(cli)
        self.assertEqual(reference["path"], "manifest:" + cli["id"])
        self.assertEqual((reference["version"], reference["sha256"]), (cli["version"], cli["sha256"]))

    def test_mcp_two_callers_inline_succeed_without_reading_server_paths(self):
        a = self.source("a.txt", b"A caller read")
        b = self.source("b.txt", b"B caller read")
        # The fixture caller performs the actual reads, as the harness does.
        items_a, items_b = [{"name": a.name, "data": a.read_bytes()}], [{"name": b.name, "data": b.read_bytes()}]
        with mock.patch.object(self.f, "_snapshot_cli", side_effect=AssertionError("server path read")):
            first = self.prepare(items_a)
            second = self.f.prepare_inline(self.receiver, "B-request", self.body, items_b,
                                            limits=self.limits, now=100)
            for forbidden in ({"name": "a.txt", "path": str(a)},
                              {"name": "a.txt", "path": str(a), "permission_evidence": {"allowed": True}},
                              {"name": "a.txt", "text": "claimed", "root": str(self.root)}):
                with self.assertRaises(self.f.FileError):
                    self.f.prepare_inline(self.receiver, "B-request", self.body, [forbidden],
                                          limits=self.limits, now=100)
        self.assertNotEqual(first["owner"], second["owner"])
        self.assertEqual(self.f.read_copy(self.receiver, second["id"], second["files"][0]["id"]), b"B caller read")
        with self.assertRaises(self.f.FileError):
            self.f.read_copy(self.receiver, first["id"], first["files"][0]["id"])

    def test_foreign_owner_is_rejected_before_copy_payload_is_read(self):
        value = self.prepare()
        original = self.f._read_file
        names = []
        def observed(folder, name, bound):
            names.append(name)
            return original(folder, name, bound)
        with mock.patch.object(self.f, "_read_file", side_effect=observed), self.assertRaises(self.f.FileError):
            self.f.read_copy(self.receiver, value["id"], value["files"][0]["id"])
        self.assertEqual(names, ["record.json"])

    def test_provisional_or_missing_identity_never_captures(self):
        for caller in (dict(self.sender, certainty="provisional"), dict(self.sender, basis="neighbor"),
                       dict(self.sender, session_id=""), None):
            with self.subTest(caller=caller), self.assertRaises(self.f.FileError):
                self.f.prepare_inline(caller, self.request, self.body, [{"name": "ok", "text": "x"}],
                                      limits=self.limits, now=100)

    def test_cli_authorized_outside_repository_hidden_and_parent_path_succeed(self):
        hidden = self.source(".review-notes", b"not a credential")
        relative = os.path.relpath(hidden, self.workspace)
        value = self.cli([relative])
        self.assertTrue(value["files"][0]["name"].startswith("."))
        self.assertEqual(self.f.read_copy(self.sender, value["id"], value["files"][0]["id"]), hidden.read_bytes())

    def test_excluded_or_unknown_source_policy_is_not_exported(self):
        path = self.source()
        for config_data in (json.dumps({"directory_excluded_paths": [str(self.artifacts)]}), '{"broken":'):
            self.paths.write_json(self.paths.path("config.json"), {})
            Path(self.paths.path("config.json")).write_text(config_data)
            with self.subTest(config=config_data), self.assertRaises(self.f.FileError):
                self.cli([str(path)])
        self.assertEqual(self.bundles("outgoing"), [])

    def test_known_credential_paths_are_rejected_without_opening_them(self):
        for path in (self.root / "apikey.env", self.root / ".ssh/id_ed25519", self.root / ".codex-9/auth.json"):
            with self.subTest(path=path), mock.patch.object(self.f, "_open_regular") as opened:
                with self.assertRaises(self.f.FileError) as failure:
                    self.cli([str(path)])
                self.assertEqual(failure.exception.code, "credential-path")
                opened.assert_not_called()

    def test_cli_os_permission_error_is_a_refusal_not_server_permission_evidence(self):
        path = self.source()
        with mock.patch.object(self.f, "_open_regular", side_effect=PermissionError(errno.EACCES, "fixture denied")):
            with self.assertRaises(self.f.FileError):
                self.cli([str(path)])
        self.assertEqual(self.bundles("outgoing"), [])

    def test_final_symlink_swap_never_captures_the_new_target(self):
        good, private = self.source("good.txt", b"allowed"), self.source("private.txt", b"private fixture")
        alias = self.artifacts / "alias.txt"
        alias.symlink_to(good)
        opened = self.f._open_regular
        def swap(path):
            alias.unlink()
            alias.symlink_to(private)
            return opened(path)
        with mock.patch.object(self.f, "_open_regular", side_effect=swap), self.assertRaises(self.f.FileError):
            self.cli([str(alias)])
        self.assertEqual(self.bundles("outgoing"), [])

    def test_parent_symlink_swap_is_rejected_before_any_source_read(self):
        public, private = self.artifacts / "public", self.artifacts / "private"
        public.mkdir(); private.mkdir()
        (public / "note").write_bytes(b"allowed")
        (private / "note").write_bytes(b"private fixture")
        opened = self.f._open_regular
        def swap(path):
            public.rename(self.artifacts / "saved-public")
            public.symlink_to(private, target_is_directory=True)
            return opened(path)
        with mock.patch.object(self.f, "_open_regular", side_effect=swap), \
                mock.patch.object(self.f.os, "read", wraps=os.read) as read:
            with self.assertRaises(self.f.FileError):
                self.cli([str(public / "note")])
            read.assert_not_called()

    def test_mutation_during_open_file_read_is_rejected(self):
        path = self.source(data=b"abcdef")
        native_read = os.read
        once = []
        def mutate(fd, length):
            data = native_read(fd, length)
            if not once:
                once.append(True)
                path.write_bytes(b"changed original")
            return data
        with mock.patch.object(self.f.os, "read", side_effect=mutate), self.assertRaises(self.f.FileError):
            self.cli([str(path)])
        self.assertEqual(self.bundles("outgoing"), [])

    def test_changed_original_during_approval_requires_new_manifest_version(self):
        path = self.source(data=b"version one")
        old = self.cli([str(path)])
        old_packet = self.packet(old)
        first = self.receive(old_packet)
        path.write_bytes(b"version two")
        with self.assertRaises(self.f.FileError):
            self.packet(old)
        newer = self.cli([str(path)], previous=old["id"])
        self.assertEqual(newer["version"], 2)
        self.assertEqual(newer["previous"], old["id"])
        self.assertNotEqual(newer["id"], old["id"])
        self.assertNotEqual(newer["sha256"], old["sha256"])
        second = self.receive(self.packet(newer))
        self.assertEqual(self.f.read_copy(self.receiver, first["storage_id"], old["files"][0]["id"], incoming=True), b"version one")
        self.assertEqual(self.f.read_copy(self.receiver, second["storage_id"], newer["files"][0]["id"], incoming=True), b"version two")
        self.assertEqual(self.f.read_copy(self.sender, old["id"], old["files"][0]["id"]), b"version one")

    def test_explicit_export_frozen_keeps_old_version_without_reopening_source(self):
        path = self.source(data=b"already read version")
        value = self.cli([str(path)])
        original_packet = self.packet(value)
        path.write_bytes(b"new version is not automatically shared")
        with self.assertRaises(self.f.FileError):
            self.packet(value)  # Fresh CLI retry still detects changed originals.
        with mock.patch.object(self.f, "_snapshot_cli", side_effect=AssertionError("frozen source read")), \
                mock.patch.object(self.f, "_open_regular", side_effect=AssertionError("frozen source open")):
            packet = self.f.export_frozen(self.sender, value["id"], self.request, self.body, now=102)
        self.assertEqual(packet, original_packet)
        self.assertEqual(packet["manifest"]["version"], value["version"])
        self.assertEqual(packet["manifest"]["sha256"], value["sha256"])
        self.assertEqual(base64.b64decode(packet["data"][value["files"][0]["id"]]), b"already read version")
        self.assertEqual(path.read_bytes(), b"new version is not automatically shared")

    def test_export_frozen_rejects_wrong_owner_body_request_expiry_and_corrupt_blob(self):
        value = self.prepare()
        for owner, request, body, now in ((self.receiver, self.request, self.body, 101),
                (self.sender, "another-request", self.body, 101),
                (self.sender, self.request, self.body + "changed", 101),
                (self.sender, self.request, self.body, 160)):
            with self.subTest(owner=owner, request=request, now=now), self.assertRaises(self.f.FileError):
                self.f.export_frozen(owner, value["id"], request, body, now=now)
        blob = next(Path(self.paths.path(self.f.DIRECTORY, "outgoing", value["id"])).glob("*.blob"))
        blob.write_bytes(b"corrupt cached bytes")
        with self.assertRaises(self.f.FileError):
            self.f.export_frozen(self.sender, value["id"], self.request, self.body, now=101)

    def test_same_name_unicode_and_case_collisions_explicitly_refuse(self):
        for names in (("same.txt", "same.txt"), ("Readme", "README"), ("é.txt", "e\u0301.txt")):
            with self.subTest(names=names), self.assertRaises(self.f.FileError) as failure:
                self.prepare([{"name": name, "text": str(index)} for index, name in enumerate(names)])
            self.assertEqual(failure.exception.code, "name-collision")
        self.assertEqual(self.bundles("outgoing"), [])

    def test_explicit_cli_aliases_handle_same_basename_without_overwriting(self):
        second = self.workspace / "source.txt"
        second.write_bytes(b"second")
        first = self.source(data=b"first")
        value = self.cli([{"path": str(first), "name": "first-source.txt"},
                          {"path": str(second), "name": "second-source.txt"}])
        self.assertEqual([e["original_name"] for e in value["files"]], ["source.txt", "source.txt"])
        receipt = self.receive(self.packet(value))
        self.assertEqual([self.f.read_copy(self.receiver, receipt["storage_id"], e["id"], incoming=True)
                          for e in value["files"]], [b"first", b"second"])

    def test_original_unicode_name_is_preserved_while_display_name_is_normalized(self):
        name = "e\u0301.txt"
        value = self.prepare([{"name": name, "text": "text"}])
        self.assertEqual(value["files"][0]["original_name"], name)
        self.assertEqual(value["files"][0]["name"], "é.txt")

    def test_traversal_or_control_names_never_become_storage_paths(self):
        for name in ("../escape", "/absolute", "..", "a/b", "a\\b", "a:b", "a\x00b", "a\nb", "a\u202eb"):
            with self.subTest(name=name), self.assertRaises(self.f.FileError):
                self.prepare([{"name": name, "text": "safe data"}])
        self.assertFalse((self.root / "escape").exists())

    def test_binary_and_empty_inline_files_roundtrip_without_text_coercion(self):
        value = self.prepare([{"name": "binary.dat", "base64": base64.b64encode(b"\x00\xff\x01").decode()},
                              {"name": "empty.txt", "data": b""}])
        receipt = self.receive(self.packet(value))
        self.assertEqual([self.f.read_copy(self.receiver, receipt["storage_id"], e["id"], incoming=True)
                          for e in value["files"]], [b"\x00\xff\x01", b""])

    def test_payload_digest_manifest_digest_and_request_binding_are_rechecked(self):
        value = self.prepare()
        packet = self.packet(value)
        cases = []
        changed = copy.deepcopy(packet)
        changed["data"][value["files"][0]["id"]] = base64.b64encode(b"different").decode()
        cases.append(changed)
        changed = copy.deepcopy(packet)
        changed["manifest"]["version"] += 1
        cases.append(changed)
        changed = copy.deepcopy(packet)
        changed["data"] = {}
        cases.append(changed)
        for case in cases:
            with self.assertRaises(self.f.FileError):
                self.receive(case)
        for updates in ({"request_id": "different-request"}, {"body": self.body + " changed"}):
            with self.assertRaises(self.f.FileError):
                self.receive(packet, **updates)
        self.assertEqual(self.bundles("incoming"), [])

    def test_sender_revalidation_rechecks_owner_and_full_body_not_preview(self):
        value = self.prepare()
        for caller, body in ((self.receiver, self.body), (self.sender, self.body + " changed")):
            with self.assertRaises(self.f.FileError):
                self.f.export_packet(caller, value["id"], request_id=self.request, body=body, now=101)

    def test_replacement_manifest_same_request_body_cannot_replace_approved_reference(self):
        old = self.prepare()
        revised = self.prepare([{"name": "review.txt", "text": "new unapproved material"}], previous=old["id"])
        with self.assertRaises(self.f.FileError) as error:
            self.receive(self.packet(revised), expected_reference=self.f.reference(old))
        self.assertEqual(error.exception.code, "reference-mismatch")
        self.assertEqual(self.bundles("incoming"), [])
        with self.assertRaises(self.f.FileError):
            self.receive(self.packet(old), expected_reference=None)

    def test_reference_uses_actual_envelope_canonical_attachment_binding(self):
        from xsm import envelope
        value = self.prepare()
        ref = self.f.reference(value)
        identity = envelope.request_identity(self.request, self.sender, self.receiver, self.body,
                                             attachments=[ref])
        canonical = identity["attachments"][0]
        self.assertEqual(canonical, [ref["path"], ref["sha256"], ref["version"], ref["size"]])
        receipt = self.receive(self.packet(value), expected_reference=canonical)
        self.assertEqual(receipt["manifest"]["sha256"], ref["sha256"])
        changed = copy.deepcopy(identity)
        changed["attachments"][0][1] = "0" * 64
        self.assertNotEqual(envelope.request_digest(identity), envelope.request_digest(changed))

    def test_same_manifest_reused_with_changed_material_never_replaces_received_copy(self):
        value = self.prepare()
        packet = self.packet(value)
        first = self.receive(packet)
        malicious = copy.deepcopy(packet)
        malicious["manifest"]["files"][0]["source_version"] = "changed-label"
        self.resign(malicious)
        with self.assertRaises(self.f.FileError) as failed:
            self.receive(malicious)
        self.assertEqual(failed.exception.code, "manifest-conflict")
        self.assertEqual(self.f.manifest(self.receiver, first["storage_id"], incoming=True), value)

    def test_malformed_signed_manifests_fail_before_storage(self):
        packet = self.packet(self.prepare())
        for mutate in (lambda v: v.update(files=[None]), lambda v: v.update(version=True),
                       lambda v: v.update(size=-1), lambda v: v.update(expires_at=float("inf")),
                       lambda v: v["files"][0].update(name="../escape"),
                       lambda v: v["files"][0].update(size=-1)):
            changed = copy.deepcopy(packet)
            mutate(changed["manifest"])
            self.resign(changed)
            with self.assertRaises(self.f.FileError):
                self.receive(changed)
        self.assertEqual(self.bundles("incoming"), [])

    def test_unknown_unsupported_and_old_capabilities_never_automatically_fallback(self):
        packet = self.packet(self.prepare())
        for capability in (None, {}, "unknown", False, {"status": "unsupported", "version": 1},
                           {"status": "observed", "version": 0}, {"status": "observed", "version": True}):
            with self.subTest(capability=capability), self.assertRaises(self.f.FileError):
                self.f.negotiate(packet, request_id=self.request, body=self.body,
                                 capability=capability, limits=self.limits)
        known = self.f.negotiate(packet, request_id=self.request, body=self.body,
                                capability={"status": "observed", "version": 1}, limits=self.limits)
        self.assertEqual(known["mode"], "files")
        self.assertFalse(known["requires_rebinding"])

    def test_explicit_inline_fallback_is_complete_and_requires_new_body_binding(self):
        value = self.prepare()
        result = self.f.negotiate(self.packet(value), request_id=self.request, body=self.body,
                                 capability=None, limits=self.limits, fallback="inline")
        self.assertEqual(result["mode"], "inline")
        self.assertTrue(result["requires_rebinding"])
        self.assertIn("exact copy\n한글", result["body"])
        self.assertIn(value["sha256"], json.dumps(result))
        self.assertNotEqual(result["binding"]["body_sha256"], value["binding"]["body_sha256"])
        with self.assertRaises(self.f.FileError):
            self.f.negotiate(self.packet(value), request_id=self.request, body=self.body,
                capability=None, limits=replace(self.limits, inline_bytes=10), fallback="inline")
        binary = self.prepare([{"name": "binary", "data": b"\xff"}])
        with self.assertRaises(self.f.FileError):
            self.f.negotiate(self.packet(binary), request_id=self.request, body=self.body,
                             capability=None, limits=self.limits, fallback="inline")

    def test_explicit_count_size_and_quota_limits_fail_without_partial_delivery(self):
        for items, limits in (([{"name": "x", "data": b"12345"}], replace(self.limits, file_bytes=4)),
                              ([{"name": "a", "text": "x"}, {"name": "b", "text": "y"}], replace(self.limits, max_files=1)),
                              ([{"name": "x", "text": "12345"}], replace(self.limits, total_bytes=4))):
            with self.assertRaises(self.f.FileError):
                self.prepare(items, limits=limits)
        packet = self.packet(self.prepare())
        with self.assertRaises(self.f.FileError) as failure:
            self.receive(packet, limits=replace(self.limits, quota_bytes=1))
        self.assertEqual(failure.exception.code, "quota-exceeded")
        self.assertEqual(failure.exception.request_id, self.request)
        self.assertFalse(failure.exception.stored)
        self.assertEqual(self.bundles("incoming"), [])

    def test_disk_full_partial_copy_rolls_back_and_does_not_report_body_success(self):
        path = self.source()
        value = self.cli([str(path)])
        packet = self.packet(value)
        write = self.f._write_file
        def full(folder, name, data):
            if name.endswith(".blob"):
                write(folder, name, data[:2])
                raise OSError(errno.ENOSPC, "fixture disk full")
            return write(folder, name, data)
        with mock.patch.object(self.f, "_write_file", side_effect=full), self.assertRaises(self.f.FileError) as failure:
            self.receive(packet)
        self.assertEqual(failure.exception.code, "disk-full")
        self.assertEqual(failure.exception.request_id, self.request)
        self.assertEqual(failure.exception.stage, "files")
        self.assertFalse(failure.exception.stored)
        self.assertEqual(self.bundles("incoming"), [])
        self.assertEqual(path.read_bytes(), b"original bytes")

    def test_rename_failure_before_commit_is_not_files_stored(self):
        packet = self.packet(self.prepare())
        with mock.patch.object(self.f.os, "rename", side_effect=OSError(errno.ENOSPC, "full")):
            with self.assertRaises(self.f.FileError):
                self.receive(packet)
        self.assertEqual(self.bundles("incoming"), [])

    def test_successful_write_of_wrong_bytes_is_detected_before_receipt(self):
        packet = self.packet(self.prepare())
        write = self.f._write_file
        def corrupt(folder, name, data):
            return write(folder, name, b"corrupted" if name.endswith(".blob") else data)
        with mock.patch.object(self.f, "_write_file", side_effect=corrupt), self.assertRaises(self.f.FileError) as failure:
            self.receive(packet)
        self.assertEqual(failure.exception.code, "copy-verification-failed")
        self.assertEqual(failure.exception.request_id, self.request)
        self.assertEqual(self.bundles("incoming"), [])

    def test_commit_symlink_swap_cannot_report_a_stored_bundle(self):
        packet = self.packet(self.prepare())
        outside = self.root / "outside-destination"
        outside.mkdir()
        (outside / "keep.txt").write_text("original")
        rename = os.rename
        displaced = []
        def swap(source, destination, **kwargs):
            parent = kwargs["src_dir_fd"]
            old = source + "-displaced"
            rename(source, old, src_dir_fd=parent, dst_dir_fd=parent)
            displaced.append(old)
            os.symlink(str(outside), source, dir_fd=parent)
            return rename(source, destination, **kwargs)
        with mock.patch.object(self.f.os, "rename", side_effect=swap), self.assertRaises(self.f.FileError) as failure:
            self.receive(packet)
        self.assertEqual(failure.exception.code, "store-changed")
        self.assertEqual((outside / "keep.txt").read_text(), "original")
        self.assertFalse(any(p.is_symlink() for p in self.bundles("incoming")))
        # The injected foreign rename left an uncommitted stage. Remove only
        # that fixture through its cache directory, never the linked original.
        for path in self.bundles("incoming"):
            if path.name in displaced:
                import shutil
                shutil.rmtree(path)

    def test_received_replay_reuses_local_id_and_expired_retention_is_not_renewed(self):
        packet = self.packet(self.prepare(limits=replace(self.limits, retention_seconds=100)))
        first = self.receive(packet, limits=replace(self.limits, retention_seconds=10))
        again = self.receive(packet, limits=replace(self.limits, retention_seconds=10), now=103)
        self.assertEqual(again["storage_id"], first["storage_id"])
        self.assertTrue(again["replayed"])
        self.assertEqual(len(self.bundles("incoming")), 1)
        with self.assertRaises(self.f.FileError):
            self.receive(packet, now=113)

    def test_post_commit_io_unknown_recovers_without_duplicate_copy(self):
        packet = self.packet(self.prepare())
        parent = Path(self.paths.path(self.f.DIRECTORY, "incoming"))
        parent_inode = parent.stat().st_ino
        sync = os.fsync
        def fail_parent(fd):
            if os.fstat(fd).st_ino == parent_inode:
                raise OSError(errno.EIO, "fixture parent sync failed after rename")
            return sync(fd)
        with mock.patch.object(self.f.os, "fsync", side_effect=fail_parent), self.assertRaises(self.f.FileError) as error:
            self.receive(packet)
        self.assertEqual(error.exception.code, "storage-unknown")
        self.assertIsNone(error.exception.stored)
        self.assertEqual(error.exception.request_id, self.request)
        self.assertEqual(len(self.bundles("incoming")), 1)
        original_id = self.bundles("incoming")[0].name
        recovered = self.receive(packet, now=103)
        self.assertTrue(recovered["replayed"])
        self.assertEqual(recovered["storage_id"], original_id)
        self.assertEqual(len(self.bundles("incoming")), 1)

    def test_capability_downgrade_keeps_previously_received_copies_readable(self):
        value = self.prepare()
        packet = self.packet(value)
        received = self.receive(packet)
        with self.assertRaises(self.f.FileError):
            self.f.negotiate(packet, request_id=self.request, body=self.body,
                             capability={"status": "unknown"}, limits=self.limits)
        self.assertEqual(self.f.manifest(self.receiver, received["storage_id"], incoming=True), value)
        self.assertEqual(self.f.read_copy(self.receiver, received["storage_id"], value["files"][0]["id"], incoming=True),
                         "exact copy\n한글".encode())

    def test_cleanup_expiry_removes_only_owned_copies_never_original(self):
        path = self.source()
        value = self.cli([str(path)])
        received = self.receive(self.packet(value))
        dry = self.f.cleanup(now=200, dry_run=True)
        self.assertEqual(len(dry["removed"]), 2)
        self.assertTrue(path.exists())
        self.assertEqual(len(self.bundles("outgoing")), 1)
        result = self.f.cleanup(now=200)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["removed"]), 2)
        self.assertEqual(path.read_bytes(), b"original bytes")
        self.assertEqual(self.bundles("incoming"), [])
        self.assertEqual(self.bundles("outgoing"), [])
        self.assertNotEqual(value["id"], received["storage_id"])

    def test_expired_outgoing_snapshot_cannot_be_exported(self):
        value = self.prepare()
        with self.assertRaises(self.f.FileError) as error:
            self.f.export_packet(self.sender, value["id"], request_id=self.request, body=self.body, now=160)
        self.assertEqual(error.exception.code, "expired")

    def test_corrupt_record_and_stale_staging_survive_until_explicit_cleanup_policy(self):
        value = self.prepare()
        record = Path(self.paths.path(self.f.DIRECTORY, "outgoing", value["id"], "record.json"))
        record.write_bytes(b'{"partial":')
        with self.assertRaises(self.f.FileError):
            self.f.manifest(self.sender, value["id"])
        stage = record.parent.parent / (".staging-" + "1" * 32)
        stage.mkdir()
        (stage / ("2" * 32 + ".blob")).write_bytes(b"partial")
        now = time.time() + 100
        result = self.f.cleanup(now=now)
        self.assertTrue(stage.exists())
        self.assertEqual(len(result["errors"]), 1)
        result = self.f.cleanup(now=now, orphan_after=10)
        self.assertFalse(stage.exists())
        self.assertTrue(record.exists(), "corrupt metadata is not proof of expiry")

    def test_m3_legacy_partial_dirs_do_not_block_other_owner_and_diagnostics_persist(self):
        packet = self.packet(self.prepare())
        parent = Path(self.paths.path(self.f.DIRECTORY, "incoming"))
        for name, record in (("4" * 32, None), ("5" * 32, b'{"partial":'),
                             ("not-a-storage-id", b'{}')):
            folder = parent / name
            folder.mkdir()
            (folder / "payload.data").write_bytes(b"old managed bytes")
            if record is not None:
                (folder / "record.json").write_bytes(record)
        incomplete = parent / ("b" * 32)
        incomplete.mkdir()
        (incomplete / "record.json").write_text(json.dumps({"owner": self.f._owner(self.receiver),
            "manifest": packet["manifest"], "expires_at": 160, "storage": None}))
        other = dict(self.receiver, session_id="different-owner")
        received = self.f.receive(other, packet, request_id=self.request, body=self.body,
            expected_reference=self.f.reference(packet["manifest"]), limits=self.limits, now=102)
        self.assertEqual(received["status"], "files-stored")
        self.assertEqual(received["store_metadata"], "unknown")
        self.assertGreaterEqual(len(received["diagnostics"]), 4)
        saved = json.loads((parent / received["storage_id"] / "record.json").read_text())
        self.assertEqual(saved["diagnostics"], received["diagnostics"])
        self.assertTrue((parent / ("4" * 32) / "payload.data").exists())
        self.assertEqual(self.f.read_copy(other, received["storage_id"], packet["manifest"]["files"][0]["id"], incoming=True),
                         "exact copy\n한글".encode())
        with self.assertRaises(self.f.FileError) as unknown:
            self.receive(packet)
        self.assertEqual(unknown.exception.code, "existing-copy-unavailable")

    def test_m3_corrupt_nonblob_nested_payload_cannot_evade_store_quota(self):
        packet = self.packet(self.prepare())
        parent = Path(self.paths.path(self.f.DIRECTORY, "incoming"))
        broken = parent / "invalid-old-folder"
        nested = broken / "nested"
        nested.mkdir(parents=True)
        (nested / "renamed-payload.data").write_bytes(b"x" * 8192)
        with self.assertRaises(self.f.FileError) as failure:
            self.receive(packet, limits=replace(self.limits, quota_bytes=8192))
        self.assertEqual(failure.exception.code, "quota-exceeded")
        self.assertTrue(failure.exception.diagnostics)
        self.assertEqual((nested / "renamed-payload.data").stat().st_size, 8192)

    def test_m3_real_sigkill_after_incoming_record_unlink_resumes_tombstone(self):
        import signal
        original_path = self.source("old-original.txt", b"old original retained")
        old = self.cli([str(original_path)])
        expired = self.receive(self.packet(old))
        active_path = self.source("active-original.txt", b"current valid original")
        active = self.cli([str(active_path)], now=1000)
        active_packet = self.f.export_packet(self.sender, active["id"], request_id=self.request, body=self.body, now=1001)
        live = self.receive(active_packet, now=1002)
        marker = self.root / "cleanup-boundary.json"
        code = r'''
import json,os,pathlib,signal,sys
from xsm import files,paths
parent=pathlib.Path(paths.path(files.DIRECTORY,'incoming'))
target=sys.argv[1]; marker=pathlib.Path(sys.argv[2])
native_listdir=os.listdir; native_unlink=os.unlink
def record_first(value):
 return sorted(native_listdir(value),key=lambda name:(name!='record.json',name))
def unlink(name,*,dir_fd=None):
 result=native_unlink(name,dir_fd=dir_fd)
 if name=='record.json' and dir_fd is not None:
  inode=os.fstat(dir_fd).st_ino
  for candidate in native_listdir(parent):
   if candidate==target or candidate.endswith('-'+target):
    stat=os.stat(parent/candidate,follow_symlinks=False)
    if stat.st_ino==inode:
     remaining=sum(os.stat(child,dir_fd=dir_fd,follow_symlinks=False).st_size for child in native_listdir(dir_fd))
     marker.write_text(json.dumps({'boundary':'after-incoming-record-unlink','entry':candidate,'remaining_bytes':remaining}))
     os.kill(os.getpid(),signal.SIGKILL)
 return result
files.os.listdir=record_first;files.os.unlink=unlink
files.cleanup(now=200)
'''
        killed = subprocess.run([sys.executable, "-c", code, expired["storage_id"], str(marker)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", XSM_HOME=self.tmp))
        self.assertEqual(killed.returncode, -signal.SIGKILL, killed.stderr)
        boundary = json.loads(marker.read_text())
        self.assertTrue(boundary["entry"].startswith(".deleting-"))
        self.assertGreater(boundary["remaining_bytes"], 0)
        parent = Path(self.paths.path(self.f.DIRECTORY, "incoming"))
        self.assertFalse((parent / expired["storage_id"]).exists())
        new = self.prepare(now=201)
        packet = self.f.export_packet(self.sender, new["id"], request_id=self.request, body=self.body, now=202)
        other = dict(self.receiver, session_id="post-crash-other-owner")
        recovered = self.f.receive(other, packet, request_id=self.request, body=self.body,
            expected_reference=self.f.reference(new), limits=self.limits, now=202)
        self.assertEqual(recovered["status"], "files-stored")
        self.f.cleanup(now=203)
        self.assertFalse((parent / boundary["entry"]).exists())
        self.assertEqual(original_path.read_bytes(), b"old original retained")
        self.assertEqual(active_path.read_bytes(), b"current valid original")
        self.assertEqual(self.f.read_copy(self.receiver, live["storage_id"], active["files"][0]["id"], incoming=True),
                         b"current valid original")

    def test_m3_pending_tombstone_usage_is_not_free_quota_and_resume_reclaims_only_it(self):
        packet = self.packet(self.prepare())
        parent = Path(self.paths.path(self.f.DIRECTORY, "incoming"))
        tomb = parent / (".deleting-" + "6" * 32 + "-" + "7" * 32)
        tomb.mkdir()
        (tomb / "retained.blob").write_bytes(b"z" * 8192)
        limited = replace(self.limits, quota_bytes=8192)
        with self.assertRaises(self.f.FileError) as error:
            self.receive(packet, limits=limited)
        self.assertEqual(error.exception.code, "quota-exceeded")
        self.f.cleanup(now=120)
        self.assertFalse(tomb.exists())
        self.assertEqual(self.receive(packet, limits=limited, now=121)["status"], "files-stored")

    def test_m3_tombstone_with_current_valid_metadata_is_not_deleted(self):
        value = self.prepare()
        current = self.receive(self.packet(value))
        parent = Path(self.paths.path(self.f.DIRECTORY, "incoming"))
        tomb = parent / (".deleting-" + "8" * 32 + "-" + current["storage_id"])
        (parent / current["storage_id"]).rename(tomb)
        result = self.f.cleanup(now=120)
        self.assertTrue(tomb.exists())
        self.assertTrue((tomb / "record.json").exists())
        self.assertTrue(result["errors"])

    def test_copy_cache_symlink_is_not_followed_for_receive_or_cleanup(self):
        packet = self.packet(self.prepare())
        parent = Path(self.paths.path(self.f.DIRECTORY, "incoming"))
        outside = self.root / "unowned-originals"
        outside.mkdir()
        original = outside / "original.txt"
        original.write_text("do not delete")
        (parent / ("3" * 32)).symlink_to(outside, target_is_directory=True)
        received = self.receive(packet)
        self.assertEqual(received["status"], "files-stored")
        self.assertEqual(received["store_metadata"], "unknown")
        self.assertTrue(received["diagnostics"])
        result = self.f.cleanup(now=1000)
        self.assertTrue(result["errors"])
        self.assertEqual(original.read_text(), "do not delete")

    def test_restart_real_process_reads_same_received_copy_and_manifest_version(self):
        value = self.prepare()
        packet_path = self.root / "packet.json"
        packet_path.write_text(json.dumps(self.packet(value)))
        receiver_state = str(self.root / "receiver-state")
        script = ('import json,sys\nfrom pathlib import Path\nfrom xsm import files\n'
                  'packet=json.loads(Path(sys.argv[1]).read_text())\n'
                  'receiver=json.loads(sys.argv[2]); limits=files.Limits(**json.loads(sys.argv[3]))\n'
                  'result=files.receive(receiver,packet,request_id=sys.argv[4],body=sys.argv[5],expected_reference=json.loads(sys.argv[6]),limits=limits,now=102)\n'
                  'data=files.read_copy(receiver,result["storage_id"],packet["manifest"]["files"][0]["id"],incoming=True)\n'
                  'assert files.manifest(receiver,result["storage_id"],incoming=True)==packet["manifest"]\n'
                  'print(json.dumps({"storage_id":result["storage_id"],"replayed":result["replayed"],"data":data.decode()}))\n')
        outputs = []
        for _ in range(2):
            result = subprocess.run([sys.executable, "-c", script, str(packet_path), json.dumps(self.receiver),
                json.dumps(asdict(self.limits)), self.request, self.body, json.dumps(self.f.reference(value))], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, timeout=10,
                env=dict(os.environ, XSM_HOME=receiver_state, PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0]["storage_id"], outputs[1]["storage_id"])
        self.assertFalse(outputs[0]["replayed"])
        self.assertTrue(outputs[1]["replayed"])
        self.assertEqual(outputs[1]["data"], "exact copy\n한글")


class FileDispatchTest(test_xsm.TempState):
    """Actual send/handoff/inbox/gate; only native queue transport is replaced."""
    def setUp(self):
        super().setUp()
        from xsm import envelope, files, handoff, inbox, ledger, receive, registry, send
        self.env, self.f, self.handoff = envelope, files, handoff
        self.inbox, self.ledger, self.receive, self.registry, self.send = inbox, ledger, receive, registry, send
        home = self.tmp + "/profile"
        os.mkdir(home)
        self.sender = registry.upsert("codex", home, "file-sender", os.getpid(), self.tmp, name="sender")
        self.target = registry.upsert("codex", home, "file-target", os.getpid(), self.tmp, name="target")
        self.limits = files.Limits(1024, 4096, 16, 32768, 60, 8192)
        self.body, self.mid = " \n자료 원문\n  ", "file-message"
        self.value = files.prepare_inline(self.sender, self.mid, self.body,
            [{"name": "검토.txt", "text": "private-copy-material"}], limits=self.limits)
        self.packet = files.export_packet(self.sender, self.value["id"], request_id=self.mid, body=self.body)
        self.refs = [files.reference(self.value)]

    def capable(self, me=None, reader=None):
        self.assertTrue(self.registry.note_capabilities(me or self.target,
            {"files": {"version": 1, "status": "observed"}}, reader_pid=reader or os.getpid()))

    def dispatch(self, **updates):
        options = dict(sender=self.sender, msg_id=self.mid, attachments=self.refs,
                       file_packet=self.packet, file_limits=self.limits)
        options.update(updates)
        return self.send.send("ref:" + self.target["ref"], self.body, **options)

    def test_scope_then_files_stored_before_native_transport_body_unchanged(self):
        from xsm import adapters
        self.capable()
        seen = []
        def native(home, sid, content):
            record = self.handoff.status(self.target, self.mid)
            storage = record["message"]["file_storage"]
            self.assertEqual(record["message"]["body"], self.body)
            self.assertEqual(record["message"]["attachments"], self.refs)
            self.assertEqual(self.f.read_copy(self.target, storage, self.value["files"][0]["id"], incoming=True),
                             b"private-copy-material")
            parsed = self.env.parse(content)
            self.assertEqual(parsed.body, self.body)
            self.assertEqual(parsed.attachments, self.refs)
            self.assertNotIn("private-copy-material", content)
            self.assertNotIn(self.tmp, content)
            seen.append((home, sid, content))
        with mock.patch.object(adapters, "to_codex", side_effect=native):
            result = self.dispatch()
        self.assertEqual(result.status, "sent-unconfirmed", result.reason)
        self.assertFalse(result.evidence["runtime_reached"], "copy storage/queue is not a receiving hook")
        self.assertEqual(len(seen), 1)
        original = self.handoff.status(self.target, self.mid)
        self.assertEqual(self.ledger.status(self.mid)["digest"], original["digest"])
        view = self.receive.take_inbox_claims(self.target)
        self.assertEqual(len(view["messages"]), 1)
        self.assertIn("[xsm_files]", view["messages"][0])
        self.assertIn(original["message"]["file_storage"], view["messages"][0])
        self.assertTrue(view["messages"][0].endswith("\n\n" + self.body))
        self.assertEqual(len(view["claims"]), 1)

    def test_unknown_capability_does_not_auto_inline_or_deliver_body(self):
        from xsm import adapters
        with mock.patch.object(adapters, "to_codex", return_value=None) as native:
            result = self.dispatch()
        self.assertEqual(result.status, "refused")
        self.assertIn("unknown", result.reason)
        native.assert_not_called()
        self.assertEqual(self.handoff.status(self.target, self.mid)["status"], "not-found")

    def test_file_copy_failure_cannot_store_body_or_claim_delivery(self):
        from xsm import adapters
        self.capable()
        with mock.patch.object(adapters, "to_codex", return_value=None) as native, \
                mock.patch.object(self.f, "receive", side_effect=self.f.FileError("disk-full", "fixture")):
            result = self.dispatch()
        self.assertEqual(result.status, "error")
        native.assert_not_called()
        self.assertEqual(self.handoff.status(self.target, self.mid)["status"], "not-found")
        self.assertEqual(self.ledger.status(self.mid)["status"], "error")
        self.assertFalse(self.ledger.evidence_of(self.mid)["runtime_reached"])
        self.assertEqual(self.inbox.count(self.target["session_id"]), 0)

    def test_post_commit_storage_unknown_keeps_body_undispatched(self):
        from xsm import adapters
        self.capable()
        failure = self.f.FileError("storage-unknown", "fixture")
        failure.stored = None
        with mock.patch.object(adapters, "to_codex", return_value=None) as native, mock.patch.object(self.f, "receive", side_effect=failure):
            result = self.dispatch()
        self.assertEqual(result.status, "unknown")
        self.assertEqual(self.ledger.status(self.mid)["status"], "unknown")
        native.assert_not_called()

    def test_permissions_are_checked_before_target_copy_side_effect(self):
        from xsm import paths
        paths.write_json(paths.path("config.json"), {"deny": [self.target["ref"]]})
        with mock.patch.object(self.f, "receive") as stored:
            result = self.dispatch()
        self.assertEqual(result.status, "refused")
        stored.assert_not_called()

    def test_mcp_inline_manifest_reuse_cannot_revalidate_cli_original_path(self):
        from xsm import context, materials
        self.capable()
        source = Path(self.tmp, ".cli-source.md")
        source.write_text("caller-readable CLI original")
        value = self.f.prepare_cli(self.sender, self.mid, self.body, [str(source)], limits=self.limits)
        call = context.of_record(self.sender, context.BASIS_SESSION)
        with mock.patch.object(self.f, "_snapshot_cli", side_effect=AssertionError("MCP attempted original path read")) as read:
            frozen=materials.prepare(self.sender, "ref:" + self.target["ref"], self.body, self.mid,
                                     source="inline", manifest_id=value["id"], call=call)
            read.assert_not_called()
        self.assertEqual(frozen['manifest_id'],value['id'])
        self.assertEqual(frozen['file_packet']['manifest'],value)
        prepared = materials.prepare(self.sender, "ref:" + self.target["ref"], self.body, self.mid,
                                     source="cli", manifest_id=value["id"], call=call)
        self.assertEqual(prepared["mode"], "files")

    def test_out_of_scope_refusal_retains_request_and_manifest_for_explicit_recovery(self):
        from xsm import paths, config, adapters
        other = self.tmp + "/target-folder"
        os.mkdir(other)
        self.target = self.registry.upsert("codex", self.target["home"], self.target["session_id"],
                                           os.getpid(), other, name="target")
        self.capable()
        with mock.patch.object(self.f, "receive") as stored:
            refused = self.dispatch()
        self.assertEqual(refused.status, "refused")
        self.assertIn(self.mid, refused.reason)
        self.assertIn(self.value["id"], refused.reason)
        stored.assert_not_called()
        config.add_link(self.tmp, other, "fixture exact target authorized before retry")
        with mock.patch.object(adapters, "to_codex", return_value=None):
            retried = self.dispatch()
        self.assertEqual(retried.status, "sent-unconfirmed", retried.reason)
        self.assertEqual(retried.msg_id, refused.msg_id)
        self.assertEqual(self.handoff.status(self.target, self.mid)["message"]["attachments"], self.refs)

    def test_remote_files_are_explicitly_unsupported_before_remote_send(self):
        from xsm import remote
        with mock.patch.object(remote, "split_target", return_value=("ref:peer", "remote-peer")), \
                mock.patch.object(remote, "send") as transport:
            result = self.dispatch()
        self.assertEqual(result.status, "refused")
        self.assertIn("P12", result.reason)
        transport.assert_not_called()

    def test_same_id_resend_preserves_refs_and_local_storage_not_new_material(self):
        from xsm import adapters
        self.capable()
        with mock.patch.object(adapters, "to_codex", return_value=None):
            first = self.dispatch()
            original = self.handoff.status(self.target, self.mid)
            repeated = self.dispatch(resend=True)
        self.assertEqual(first.status, "sent-unconfirmed")
        self.assertEqual(repeated.status, "sent-unconfirmed", repeated.reason)
        self.assertEqual(self.handoff.status(self.target, self.mid)["message"], original["message"])
        changed = self.f.prepare_inline(self.sender, self.mid, self.body,
            [{"name": "different.txt", "text": "unapproved"}], limits=self.limits, previous=self.value["id"])
        packet = self.f.export_packet(self.sender, changed["id"], request_id=self.mid, body=self.body)
        with mock.patch.object(self.f, "receive") as store:
            result = self.dispatch(resend=True, attachments=[self.f.reference(changed)], file_packet=packet)
        self.assertEqual(result.status, "refused")
        store.assert_not_called()
        self.assertEqual(self.handoff.status(self.target, self.mid)["message"], original["message"])

    def test_strict_fyi_stores_file_copies_without_native_queue_or_export(self):
        from xsm import adapters
        self.capable()
        with mock.patch.object(adapters, "to_codex", return_value=None) as native:
            result = self.dispatch(wake=False)
        self.assertEqual(result.status, "stored", result.reason)
        native.assert_not_called()
        self.assertEqual(self.inbox.count(self.target["session_id"]), 0)
        record = self.handoff.status(self.target, self.mid)
        self.assertTrue(record["message"]["file_storage"])
        view = self.receive.take_inbox_claims(self.target, passive_only=True)
        self.assertEqual(len(view["messages"]), 1)
        self.assertIn("xsm_files", view["messages"][0])

    def test_missing_target_files_cannot_receive_a_delivered_body(self):
        from xsm import adapters
        self.capable()
        with mock.patch.object(adapters, "to_codex", return_value=None) as transport:
            self.assertEqual(self.dispatch().status, "sent-unconfirmed")
        parsed = self.env.parse(transport.call_args.args[2])
        self.f.cleanup(now=time.time() + 1000)
        self.assertEqual(self.receive.check(parsed, self.registry.by_session("codex", "file-target"))[0], "block")
        self.assertFalse(self.ledger.received(self.mid))

    def test_ref_codec_is_bounded_rejects_invalid_and_received_digest_includes_refs(self):
        import base64
        wire = self.env.build(self.body, msg_id=self.mid, sender=self.sender, scope="fixture", attachments=self.refs)
        parsed = self.env.parse(wire)
        self.assertEqual(parsed.attachments, self.refs)
        modified = copy.deepcopy(self.refs)
        modified[0]["sha256"] = "0" * 64
        other = self.env.parse(self.env.build(self.body, msg_id=self.mid, sender=self.sender,
                                             scope="fixture", attachments=modified))
        self.assertNotEqual(self.env.received_digest(parsed.header, parsed.body, parsed.attrs),
                            self.env.received_digest(other.header, other.body, other.attrs))
        encoded = parsed.header["files"]
        for bad in ("?", "-", "A" * (self.env.FILE_REFS_BOUND * 2),
                    base64.urlsafe_b64encode(b'null').decode().rstrip("="),
                    base64.urlsafe_b64encode(b'{}').decode().rstrip("=")):
            candidate = self.env.parse(wire.replace("files=" + encoded, "files=" + bad))
            self.assertTrue(candidate.error)
            self.assertEqual(self.receive.check(candidate, self.target)[0], "block")

    def test_supplementary_cf_roundtrips_metadata_without_mutating_core_identity(self):
        name = "peer\U000e0001"
        sender = dict(self.sender, name=name, alias="alias")
        wire = self.env.build(self.body, msg_id=self.mid, sender=sender, scope="fixture", attachments=self.refs)
        self.assertNotIn("\U000e0001", wire)
        parsed = self.env.parse(wire)
        self.assertEqual(parsed.attrs["from-name"], name + "@alias")
        self.assertEqual(parsed.header["from"], name + "@alias")
        self.assertEqual(parsed.header["ref"], self.sender["ref"])
        self.assertEqual(parsed.attrs["from-session"], self.sender["session_id"])
        self.assertEqual(parsed.body, self.body)
        self.assertEqual(parsed.attachments, self.refs)
        self.assertIn("\\U000e0001", wire)

    def test_capability_note_exact_generation_only_and_no_global_registry_lookup(self):
        with mock.patch.object(self.registry, "records", side_effect=AssertionError("global scan")), \
                mock.patch.object(self.registry, "by_session", side_effect=AssertionError("re-resolve")), \
                mock.patch.object(self.registry, "_enrich", side_effect=AssertionError("re-enrich")):
            self.capable()
            self.assertEqual(self.registry.file_capability(self.target)["status"], "observed")
            for invalid in ({}, dict(self.target, basis="neighbor"), dict(self.target, certainty="provisional"),
                            dict(self.target, session_id="different"), dict(self.target, home=self.tmp + "/other")):
                self.assertFalse(self.registry.note_capabilities(invalid,
                    {"files": {"version": 1, "status": "observed"}}, reader_pid=os.getpid()))
        self.assertEqual(self.registry.file_capability(self.target)["status"], "observed")

    def test_dead_reader_or_new_native_generation_degrades_capability_to_unknown(self):
        from xsm import paths
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.capable(reader=child.pid)
            self.assertEqual(self.registry.file_capability(self.target)["status"], "observed")
        finally:
            child.terminate(); child.wait(timeout=3)
        self.assertEqual(self.registry.file_capability(self.target)["status"], "unknown")
        self.capable()
        native = dict(self.target, lstart="new execution generation")
        paths.write_json(self.registry._record_path("codex", self.target["session_id"]), native)
        self.assertEqual(self.registry.file_capability(self.target)["status"], "unknown")
