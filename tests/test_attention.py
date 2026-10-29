"""Attention evidence with a controlled OS runner, never an actual notification."""
import hashlib
import subprocess
import threading
from unittest import mock

from tests import test_xsm


class AttentionTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import attention, paths
        self.a, self.paths = attention, paths

    def saved(self, key="decision"):
        return self.paths.read_json(self.paths.path("attention", self.key(key) + ".json"))

    @staticmethod
    def key(label):
        return hashlib.sha256(label.encode()).hexdigest()

    def notify(self, key, title, body, **kwargs):
        return self.a.notify(self.key(key), title, body, **kwargs)

    def test_default_off_never_calls_os_and_never_claims_human_saw(self):
        runner = mock.Mock()
        result = self.notify("decision", "title", "body", runner=runner)
        runner.assert_not_called()
        self.assertEqual((result["status"], result["reason"]), ("suppressed", "disabled"))
        self.assertNotIn("os_called_at", result)
        self.assertIsNone(result["human_saw"])
        self.assertEqual(self.saved(), result)

    def test_success_is_only_os_call_success_and_untrusted_text_stays_argv(self):
        title, body = 'quoted " title', 'body\n"; display alert "not code"'
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        result = self.notify("decision", title, body, enabled=True, runner=runner)
        args, kwargs = runner.call_args
        self.assertEqual(args[0][-2:], [title, body])
        self.assertNotIn(body, args[0][2])
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(result["status"], "os-call-succeeded")
        self.assertIsNone(result["human_saw"])
        self.assertIsNone(self.saved()["human_saw"])

    def test_frequency_suppression_does_not_reset_original_window(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        with mock.patch.object(self.a.time, "time", return_value=100):
            self.notify("decision", "title", "body", enabled=True, interval=60, runner=runner)
        with mock.patch.object(self.a.time, "time", return_value=159):
            result = self.notify("decision", "title", "body", enabled=True, interval=60, runner=runner)
        self.assertEqual((result["status"], result["reason"]), ("suppressed", "frequency"))
        self.assertEqual(result["os_called_at"], 100)
        self.assertEqual(runner.call_count, 1)
        with mock.patch.object(self.a.time, "time", return_value=160):
            retry = self.notify("decision", "title", "body", enabled=True, interval=60, runner=runner)
        self.assertEqual(retry["status"], "os-call-succeeded")
        self.assertEqual(runner.call_count, 2)
        self.assertIsNone(retry["human_saw"])

    def test_failure_is_durable_and_frequency_limited_then_retryable(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 7))
        with mock.patch.object(self.a.time, "time", return_value=100):
            failed = self.notify("decision", "title", "body", enabled=True, runner=runner)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["exit_code"], 7)
        self.assertIsNone(failed["human_saw"])
        with mock.patch.object(self.a.time, "time", return_value=110):
            suppressed = self.notify("decision", "title", "body", enabled=True, runner=runner)
        self.assertEqual(suppressed["reason"], "frequency")
        self.assertEqual(runner.call_count, 1)
        runner.return_value = subprocess.CompletedProcess([], 0)
        with mock.patch.object(self.a.time, "time", return_value=160):
            recovered = self.notify("decision", "title", "body", enabled=True, runner=runner)
        self.assertEqual(recovered["status"], "os-call-succeeded")
        self.assertIsNone(recovered["human_saw"])

    def test_unavailable_os_or_timeout_is_failure_not_human_ack(self):
        for exc in (OSError("desktop absent"), subprocess.TimeoutExpired("osascript", 5)):
            with self.subTest(exception=type(exc).__name__):
                key = type(exc).__name__
                runner = mock.Mock(side_effect=exc)
                result = self.notify(key, "title", "body", enabled=True, runner=runner)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["reason"], type(exc).__name__)
                self.assertIsNone(result["human_saw"])
                self.assertIsNone(self.saved(key)["human_saw"])

    def test_delayed_runner_persists_requested_before_success_or_failure(self):
        for code in (0, 3):
            with self.subTest(exit_code=code):
                entered, release = threading.Event(), threading.Event()
                replies, errors = [], []
                key = "delayed-%d" % code
                def runner(*args, **kwargs):
                    entered.set()
                    if not release.wait(3):
                        raise subprocess.TimeoutExpired("fixture barrier", 3)
                    return subprocess.CompletedProcess([], code)
                def call():
                    try:
                        replies.append(self.notify(key, "title", "body", enabled=True, runner=runner))
                    except Exception as exc:
                        errors.append(exc)
                thread = threading.Thread(target=call)
                thread.start()
                try:
                    self.assertTrue(entered.wait(2))
                    self.assertTrue(thread.is_alive())
                    self.assertEqual(replies, [], "notify cannot return success before the OS call finishes")
                    state = self.saved(key)
                    self.assertEqual(state["status"], "requested")
                    self.assertIsNone(state["human_saw"])
                    duplicate = mock.Mock()
                    result = self.notify(key, "title", "body", enabled=True, runner=duplicate)
                    self.assertEqual(result["reason"], "frequency")
                    duplicate.assert_not_called()
                finally:
                    release.set()
                    thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(replies[0]["status"], "os-call-succeeded" if code == 0 else "failed")
                self.assertIsNone(replies[0]["human_saw"])
                self.assertEqual(self.saved(key), replies[0])

    def test_disabled_request_does_not_fabricate_or_forget_prior_os_attempt(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        with mock.patch.object(self.a.time, "time", return_value=100):
            self.notify("decision", "title", "body", enabled=True, runner=runner)
        with mock.patch.object(self.a.time, "time", return_value=110):
            result = self.notify("decision", "title", "body", runner=runner)
        self.assertEqual(result["reason"], "disabled")
        self.assertEqual(result["os_called_at"], 100)
        self.assertIsNone(result["human_saw"])
        self.assertEqual(runner.call_count, 1)
