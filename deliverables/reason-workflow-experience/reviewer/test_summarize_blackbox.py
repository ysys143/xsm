"""Contract-v1 CLI tests, authored without reading the implementation.

Run: python3 -m unittest -v test_summarize_blackbox
Override CLI path with MESSAGE_AUDIT_CLI if testing a separate candidate.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
CLI = Path(os.environ.get("MESSAGE_AUDIT_CLI", HERE.parent / "message-audit" / "summarize.py"))
SUCCESS_KEYS = {"request_count", "answered", "unanswered", "orphan_replies"}


class SummarizeContractTests(unittest.TestCase):
    def invoke(self, payload, stdin=False, options=()):
        self.assertTrue(CLI.is_file(), f"CLI implementation is missing: {CLI}")
        if stdin:
            return subprocess.run(
                [sys.executable, str(CLI), *options, "-"], input=payload,
                encoding="utf-8", capture_output=True, cwd=HERE, timeout=10,
            )
        with tempfile.TemporaryDirectory(prefix="audit-input-", dir=HERE) as folder:
            path = Path(folder) / "input.jsonl"
            path.write_text(payload, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(CLI), *options, str(path)], encoding="utf-8",
                capture_output=True, cwd=HERE, timeout=10,
            )

    def assert_summary(self, records, *, answered=(), unanswered=(), orphans=(), stdin=False,
                       options=(), expected_exit=0):
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
        return self.assert_payload(payload, answered=answered, unanswered=unanswered,
                                   orphans=orphans, stdin=stdin, options=options,
                                   expected_exit=expected_exit)

    def assert_payload(self, payload, *, answered=(), unanswered=(), orphans=(), stdin=False,
                       options=(), expected_exit=0):
        result = self.invoke(payload, stdin=stdin, options=options)
        self.assertEqual(result.returncode, expected_exit, result.stderr)
        try:
            actual = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"Expected exactly one JSON object: {exc}; stdout={result.stdout!r}")
        self.assertEqual(actual, {
            "request_count": len(answered) + len(unanswered),
            "answered": list(answered),
            "unanswered": list(unanswered),
            "orphan_replies": list(orphans),
        })
        self.assertIs(type(actual["request_count"]), int)

    def assert_invalid(self, payload, line, *, stdin=False, options=()):
        result = self.invoke(payload, stdin=stdin, options=options)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertRegex(result.stderr, rf"(?<![0-9]){line}(?![0-9])")
        # Error diagnostics may use stdout, but must never include success JSON.
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", result.stdout):
            try:
                value, _ = decoder.raw_decode(result.stdout[match.start():])
            except json.JSONDecodeError:
                continue
            self.assertFalse(isinstance(value, dict) and SUCCESS_KEYS <= value.keys(),
                             f"Invalid input emitted success JSON: {result.stdout!r}")

    def test_normal_round_trip(self):
        self.assert_summary([{"id": "request"}, {"id": "reply", "reply_to": "request"}],
                            answered=["request"])

    def test_unanswered_requests_and_lexicographic_order(self):
        self.assert_summary([{"id": "z"}, {"id": "A"}, {"id": "a"}],
                            unanswered=["A", "a", "z"])

    def test_orphan_reply_ids_are_sorted_not_target_ids(self):
        self.assert_summary([{"id": "z-reply", "reply_to": "A-missing"},
                             {"id": "a-reply", "reply_to": "Z-missing"}],
                            orphans=["a-reply", "z-reply"])

    def test_reply_before_request_and_supplied_example(self):
        self.assert_summary([
            {"id": "req-2", "body": "Investigate delivery semantics"},
            {"id": "answer-1", "reply_to": "req-1", "body": "The gate recorded handoff"},
            {"id": "req-1", "body": "Does delivered mean completed?"},
            {"id": "orphan-1", "reply_to": "missing"},
        ], answered=["req-1"], unanswered=["req-2"], orphans=["orphan-1"])

    def test_reply_to_existing_reply_is_not_orphan(self):
        self.assert_summary([{"id": "leaf", "reply_to": "middle"},
                             {"id": "middle", "reply_to": "root"}, {"id": "root"}],
                            answered=["root"])

    def test_reply_to_orphan_reply_is_not_itself_orphan(self):
        self.assert_summary([{"id": "leaf", "reply_to": "middle"},
                             {"id": "middle", "reply_to": "absent"}, {"id": "root"}],
                            unanswered=["root"], orphans=["middle"])

    def test_multiple_direct_replies_count_root_once(self):
        self.assert_summary([{"id": "r"}, {"id": "a1", "reply_to": "r"},
                             {"id": "a2", "reply_to": "r"}], answered=["r"])

    def test_duplicate_roots_normalize_missing_and_null(self):
        self.assert_summary([{"id": "r", "body": "first"},
                             {"id": "r", "reply_to": None, "body": "changed"},
                             {"id": "r"}], unanswered=["r"])

    def test_duplicate_replies_and_orphans_are_ignored(self):
        self.assert_summary([{"id": "r"}, {"id": "a", "reply_to": "r"},
                             {"id": "a", "reply_to": "r", "extra": [1]},
                             {"id": "o", "reply_to": "missing"},
                             {"id": "o", "reply_to": "missing"}],
                            answered=["r"], orphans=["o"])

    def test_conflicting_duplicate_different_targets(self):
        self.assert_invalid('{"id":"a","reply_to":"x"}\n\n{"id":"a","reply_to":"y"}\n', 3)

    def test_conflicting_duplicate_root_then_reply(self):
        self.assert_invalid('{"id":"a"}\n{"id":"a","reply_to":"x"}\n', 2)

    def test_conflicting_duplicate_reply_then_root(self):
        self.assert_invalid('{"id":"a","reply_to":"x"}\n{"id":"a","reply_to":null}\n', 2)

    def test_invalid_json_reports_physical_line_and_no_partial_summary(self):
        self.assert_invalid('\n{"id":"valid"}\n \t\n{broken\n', 4)

    def test_each_nonblank_line_must_be_an_object(self):
        for value in (None, [], "root", 7, True):
            with self.subTest(value=value):
                self.assert_invalid('\n' + json.dumps(value) + '\n', 2)

    def test_id_must_be_present_nonempty_string(self):
        for row in ({}, {"id": None}, {"id": ""}, {"id": 0}, {"id": False},
                    {"id": []}, {"id": {}}):
            with self.subTest(row=row):
                self.assert_invalid(json.dumps(row) + '\n', 1)

    def test_reply_to_must_be_null_or_nonempty_string(self):
        for value in ("", 0, False, [], {}):
            with self.subTest(value=value):
                self.assert_invalid(json.dumps({"id": "r", "reply_to": value}) + '\n', 1)

    def test_empty_file(self):
        self.assert_payload("")

    def test_blank_lines_are_ignored(self):
        self.assert_payload('\n \t\r\n{"id":"r"}\n\n', unanswered=["r"])

    def test_only_blank_lines(self):
        self.assert_payload('\n \t\n\r\n')

    def test_stdin_with_unicode_ids(self):
        self.assert_summary([{"id": "요청"}, {"id": "답변", "reply_to": "요청"},
                             {"id": "미응답"}], answered=["요청"],
                            unanswered=["미응답"], stdin=True)

    def test_empty_stdin(self):
        self.assert_payload("", stdin=True)

    def test_invalid_stdin(self):
        self.assert_invalid('\nnot-json\n', 2, stdin=True)

    def test_unrelated_fields_are_ignored(self):
        self.assert_summary([{"id": "r", "answered": True, "replyTo": "missing",
                              "payload": {"reply_to": 0}, "extra": [False, None]}],
                            unanswered=["r"])

    def test_nonempty_whitespace_ids_and_targets_are_not_trimmed(self):
        self.assert_summary([{"id": " "}, {"id": "r"},
                             {"id": "a", "reply_to": " "},
                             {"id": "o", "reply_to": " r"}],
                            answered=[" "], unanswered=["r"], orphans=["o"])

    def test_self_reference_and_cycle_have_existing_targets(self):
        self.assert_summary([{"id": "self", "reply_to": "self"},
                             {"id": "x", "reply_to": "y"},
                             {"id": "y", "reply_to": "x"}])

    def test_answered_ids_are_sorted(self):
        self.assert_summary([{"id": "z"}, {"id": "a"}, {"id": "m"},
                             {"id": "az", "reply_to": "z"},
                             {"id": "aa", "reply_to": "a"},
                             {"id": "am", "reply_to": "m"}],
                            answered=["a", "m", "z"])

    def test_v2_fail_on_unanswered_still_emits_summary_and_exits_3(self):
        self.assert_summary([{"id": "z"}, {"id": "a"},
                             {"id": "answer", "reply_to": "a"},
                             {"id": "orphan", "reply_to": "missing"}],
                            answered=["a"], unanswered=["z"], orphans=["orphan"],
                            options=["--fail-on-unanswered"], expected_exit=3)

    def test_v2_fail_on_unanswered_without_unanswered_exits_0(self):
        self.assert_summary([{"id": "root"}, {"id": "reply", "reply_to": "root"},
                             {"id": "orphan", "reply_to": "missing"}],
                            answered=["root"], orphans=["orphan"], stdin=True,
                            options=["--fail-on-unanswered"])

    def test_v2_fail_on_unanswered_invalid_input_still_exits_2(self):
        # A preceding unanswered root must not cause an invalid input to exit 3.
        self.assert_invalid('{"id":"unanswered"}\n\n{broken\n', 3,
                            options=["--fail-on-unanswered"])


if __name__ == "__main__":
    unittest.main()
