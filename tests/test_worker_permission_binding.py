"""One native invocation can have several hooks, never several approvals."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from tests.test_xsm import TempState


class WorkerPermissionBindingTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import workers, paths
        self.w, self.paths = workers, paths
        self.worker = {"name": "test-worker", "runtime": "claude", "mode": "background",
                       "session_id": "native-worker", "home": self.tmp, "pid": os.getpid(),
                       "lstart": "generation-one", "parent_ref": "parent", "approval_timeout": 0.01}
        self.transcript = Path(self.tmp) / "native-worker.jsonl"
        self.input = {"file_path": self.tmp + "/outside.txt", "content": "probe"}
        self.data = {"session_id": "native-worker", "prompt_id": "prompt-one",
                     "transcript_path": str(self.transcript), "tool_name": "Write", "tool_input": self.input}
        self.rows = [{"type": "user", "sessionId": "native-worker", "promptId": "prompt-one",
                      "message": {"role": "user", "content": "run the temporary probe"}}]
        self.add_call("call-one")
        self.write_rows()
        for patch in (mock.patch.dict(os.environ, {"XSM_WORKER": "test-worker"}),
                      mock.patch.object(workers, "load", return_value=self.worker),
                      mock.patch.object(workers, "_notify_parent")):
            patch.start()
            self.addCleanup(patch.stop)

    def add_call(self, call_id):
        self.rows.append({"type": "assistant", "sessionId": "native-worker", "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": call_id,
                "name": "Write", "input": self.input}]}})

    def write_rows(self):
        self.transcript.write_text("".join(json.dumps(row) + "\n" for row in self.rows))

    def requests(self):
        return [json.loads(p.read_text()) for p in Path(self.paths.path(self.w.APPROVALS)).glob("*.json")]

    def test_duplicate_native_hooks_share_one_request(self):
        for _ in range(2):
            self.w.permission_request(self.data, "claude")
        self.assertEqual(len(self.requests()), 1)

    def test_concurrent_callbacks_share_the_request_and_original_deadline(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.w.permission_request(self.data, "claude"), range(2)))
        requests = self.requests()
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["status"], "denied")
        self.assertAlmostEqual(requests[0]["expires_at"] - requests[0]["t"], 0.01, places=5)
        self.assertTrue(all(r["hookSpecificOutput"]["decision"]["behavior"] == "deny" for r in replies))

    def test_native_permission_cannot_be_approved_after_its_deadline(self):
        from xsm import native_permissions
        identity = native_permissions.identify(self.worker, self.data, "claude")
        request_id = native_permissions.key(identity)[:16]
        request = {"id": request_id, "worker": self.worker["name"], "status": "pending",
                   "native_identity": identity, "expires_at": time.time() - 1}
        self.paths.write_json(self.w._approval_path(request_id), request)
        with self.assertRaises(self.w.WorkerError):
            self.w.answer_asked(request_id, True, "parent")
        self.assertEqual(self.requests()[0]["status"], "denied")

    def test_duplicate_denied_callbacks_notify_the_parent_once(self):
        from xsm import native_permissions
        identity = native_permissions.identify(self.worker, self.data, "claude")
        request_id = native_permissions.key(identity)[:16]
        request = {"id": request_id, "worker": self.worker["name"], "runtime": "claude",
                   "tool": "Write", "input": self.input, "summary": "Write: temporary probe",
                   "status": "denied", "reason": "user said no", "t": time.time(),
                   "native_identity": identity, "expires_at": time.time() + 30}
        self.paths.write_json(self.w._approval_path(request_id), request)
        with mock.patch.object(self.w, "_notify_parent") as notify:
            for _ in range(2):
                self.w.permission_request(self.data, "claude")
        self.assertEqual(notify.call_count, 1)
        self.assertIn("user said no", notify.call_args.kwargs["outcome"])

    def test_disappeared_request_fails_closed_without_waiting_forever(self):
        def remove_request(worker, req):
            os.unlink(self.w._approval_path(req["id"]))
        with mock.patch.object(self.w, "_notify_parent", side_effect=remove_request), \
                mock.patch.object(self.w.time, "sleep", side_effect=RuntimeError("must not wait")):
            reply = self.w.permission_request(self.data, "claude")
        decision = reply["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "deny")
        self.assertIn("disappeared", decision["message"])

    def test_identical_input_from_a_different_native_call_is_not_merged(self):
        self.w.permission_request(self.data, "claude")
        self.rows.append({"type": "user", "sessionId": "native-worker", "promptId": "prompt-one",
                          "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call-one"}]}})
        self.add_call("call-two")
        self.write_rows()
        self.w.permission_request(self.data, "claude")
        self.assertEqual(len(self.requests()), 2)

    def test_indistinguishable_parallel_calls_are_not_guessed(self):
        self.add_call("call-two")
        self.write_rows()
        self.w.permission_request(self.data, "claude")
        self.assertEqual(self.requests(), [])

    def test_background_question_tool_is_redirected_without_a_permission_form(self):
        reply = self.w.permission_request(dict(self.data, tool_name="AskUserQuestion"), "claude")
        decision = reply["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "deny")
        self.assertIn("no person at its terminal", decision["message"])
        self.assertEqual(self.requests(), [])

    def observed(self, event, call_id):
        from xsm import receive
        receive._handle(dict(self.data, hook_event_name=event, tool_use_id=call_id))

    def test_pre_tool_identity_works_before_the_native_transcript_is_flushed(self):
        self.rows = self.rows[:1]
        self.write_rows()
        self.observed("PreToolUse", "early-call")
        self.w.permission_request(self.data, "claude")
        self.w.permission_request(self.data, "claude")
        self.assertEqual(len(self.requests()), 1)
        self.assertEqual(self.requests()[0]["native_identity"]["tool_use_id"], "early-call")

    def test_completed_and_failed_calls_retire_before_the_next_identical_call(self):
        for event in ("PostToolUse", "PostToolUseFailure"):
            call_id = "first-" + event
            self.observed("PreToolUse", call_id)
            self.w.permission_request(self.data, "claude")
            self.observed(event, call_id)
        self.assertEqual(len(self.requests()), 2)

    def test_observed_parallel_calls_cannot_fall_back_to_one_flushed_call(self):
        self.observed("PreToolUse", "call-one")
        self.observed("PreToolUse", "call-two")
        self.w.permission_request(self.data, "claude")
        self.assertEqual(self.requests(), [])

    def test_observed_identity_cannot_cross_a_worker_generation(self):
        self.observed("PreToolUse", "call-one")
        self.worker["lstart"] = "generation-two"
        self.w.permission_request(self.data, "claude")
        self.assertEqual(self.requests(), [])

    def test_new_native_prompt_retires_the_previous_prompts_metadata(self):
        self.observed("PreToolUse", "old-call")
        self.data["prompt_id"] = "prompt-two"
        self.observed("PreToolUse", "new-call")
        self.w.permission_request(self.data, "claude")
        self.assertEqual(len(self.requests()), 1)
        self.assertEqual(self.requests()[0]["native_identity"]["tool_use_id"], "new-call")

    def test_observation_is_bounded_and_fails_closed_when_full(self):
        from xsm import native_permissions
        with mock.patch.object(native_permissions, "MAX_OPEN_CALLS", 2):
            for n in range(3):
                self.observed("PreToolUse", "call-%s" % n)
        self.w.permission_request(self.data, "claude")
        state = self.paths.read_json(native_permissions._state_path(self.worker))
        self.assertEqual(len(state["calls"]), 2)
        self.assertTrue(state["invalid"])
        self.assertEqual(self.requests(), [])

    def test_worker_settings_observe_identity_without_altering_permission_rules(self):
        worker = dict(self.worker, full_access=False)
        os.makedirs(self.w._dir(worker["name"]), exist_ok=True)
        settings = self.paths.read_json(self.w._claude_worker_settings(worker))
        self.assertEqual(set(settings["hooks"]), {"PermissionRequest", "PreToolUse", "PostToolUse", "PostToolUseFailure"})
        self.assertTrue(settings["sandbox"]["enabled"])
        self.assertFalse(settings["sandbox"]["allowUnsandboxedCommands"])
