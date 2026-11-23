"""#29: a refused send is kept in the sender's outbox, not in a receiver's held list,
and the words, the commands and the list say so."""
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import test_one_yes  # noqa: E402

_Sessions = test_one_yes._Sessions


class OutboxWordsTest(_Sessions):
    def test_refusal_names_the_outbox_and_the_command_that_resumes_it(self):
        code, text = self._send()
        self.assertEqual(code, 2, text)
        msg_id = self._held_id(text)
        self.assertIn("kept unsent as %s" % msg_id, text)
        self.assertNotIn("held as", text, "'held' is the receiver's list")
        self.assertIn("`xsm held deliver` does not take it", text)
        self.assertIn("running the same `xsm send` again does", text)
        self.assertIn("`xsm send --held %s`" % msg_id, text)

    def test_held_deliver_with_an_outbox_id_points_to_send(self):
        code, text = self._send()
        msg_id = self._held_id(text)
        code, said = self._cli("held", "deliver", msg_id)
        self.assertEqual(code, 2, said)
        self.assertIn("no such held message", said)
        self.assertIn("one of your own unsent messages", said)
        self.assertIn("xsm send --held %s" % msg_id, said)

    def test_held_deliver_with_an_unknown_id_stays_plain(self):
        code, said = self._cli("held", "deliver", "0123456789abcdef")
        self.assertEqual(code, 2, said)
        self.assertEqual(said.strip(), "no such held message")

    def test_another_sessions_outbox_id_is_not_confirmed(self):
        code, text = self._send()
        msg_id = self._held_id(text)
        from unittest import mock
        from xsm import registry
        with mock.patch.object(registry, "me", return_value=self.you):
            code, said = self._cli("held", "deliver", msg_id)
        self.assertEqual(said.strip(), "no such held message", "its existence stays private")


class ReplacedAnswerTest(_Sessions):
    def test_a_later_message_that_replaced_the_answer_is_said_to_have_replaced_it(self):
        code, text = self._send()
        self._reply("응, 연결하고 보내")
        self._reply("지금 상태가 어때?")
        code, shown = self._send()
        self.assertEqual(code, 2, shown)
        self.assertIn('your user replied: "지금 상태가 어때?"', shown)
        self.assertIn('replaced their earlier answer "응, 연결하고 보내"', shown)
        self.assertIn("unless this reply is a yes, ask them again", shown)

    def test_an_answer_nobody_replaced_has_no_such_note(self):
        self._send()
        self._reply("응")
        code, shown = self._send()
        self.assertNotIn("replaced their earlier answer", shown)


class StoppedWhyTest(_Sessions):
    def test_a_stale_refusal_says_it_is_about_the_process_not_the_scope(self):
        from xsm import send
        text = send.stopped_why({"state": "stale", "state_why": "pid_dead"})
        self.assertIn("its recorded process is gone", text)
        self.assertIn("`xsm link` and `xsm unlink` do not change it", text)

    def test_a_send_to_a_stopped_session_carries_the_reason_through_the_registry(self):
        from unittest import mock
        from xsm import config, identity
        config.add_link(self.a, self.b, "test")
        real = identity.state_reason

        def stopped(record):
            return ("stale", "socket_dead") if record.get("session_id") == "s-target" else real(record)
        with mock.patch.object(identity, "state_reason", stopped):
            code, text = self._send()
        self.assertEqual(code, 2, text)
        self.assertIn("is not running (stale)", text)
        self.assertIn("xsm reads it as stopped because its Claude Code socket does not answer", text)

    def test_unlink_leaves_the_session_live_and_the_send_says_out_of_scope(self):
        from xsm import config
        config.add_link(self.a, self.b, "test")
        code, _ = self._cli("unlink", self.b)
        self.assertEqual(code, 0)
        code, text = self._send()
        self.assertIn("out of scope", text)
        self.assertNotIn("not running", text)


class HeldListTest(_Sessions):
    def _hold(self, name, receiver_ref, reason="the sender is not linked", t=None):
        from xsm import paths
        paths.write_json(paths.path(paths.HELD, "%s.json" % name), {
            "t": t or time.time(), "reason": reason, "runtime": "claude",
            "receiver": "sender", "receiver_ref": receiver_ref, "id": "m-" + name,
            "from": "someone", "body": "hello %s" % name})

    def test_the_list_shows_this_sessions_messages_and_counts_the_rest(self):
        self._hold("mine1", self.me["ref"])
        self._hold("theirs1", self.you["ref"])
        self._hold("theirs2", self.you["ref"])
        code, text = self._cli("held", "list")
        self.assertIn("mine1", text)
        self.assertNotIn("theirs1", text)
        self.assertIn("2 more held for other sessions", text)
        self.assertIn("xsm held list --all", text)
        code, everything = self._cli("held", "list", "--all")
        for name in ("mine1", "theirs1", "theirs2"):
            self.assertIn(name, everything)
        self.assertNotIn("more held for other sessions", everything)

    def test_the_table_has_an_id_column_and_the_same_filter(self):
        self._hold("mine1", self.me["ref"])
        self._hold("theirs1", self.you["ref"])
        code, text = self._cli("held", "list", "--table")
        self.assertIn("| id | from | why it was held | message |", text)
        self.assertIn("mine1", text)
        self.assertNotIn("theirs1", text)

    def _person(self):
        """The command is typed by a person at a terminal, who needs no one's yes."""
        from unittest import mock
        from xsm import workers
        patch = mock.patch.object(workers, "human_terminal", return_value=True)
        patch.start()
        self.addCleanup(patch.stop)

    OLD = 2 * 86400.0

    def test_prune_drops_old_gone_sessions_and_socket_mismatches_and_can_restore_them(self):
        from xsm import paths, receive
        self._person()
        old = time.time() - self.OLD
        self._hold("keep", self.you["ref"])        # the Codex session is live here
        self._hold("sock", self.you["ref"], t=old, reason="the message came from uds:/tmp/x.sock, %s 'a'"
                   % receive.SOCKET_MISMATCH)
        self._hold("gone", "ffffff", t=old)
        code, text = self._cli("held", "prune", "--all", "--dry-run")
        self.assertIn("would drop sock", text)
        self.assertIn("would drop gone", text)
        self.assertTrue(os.path.exists(paths.path(paths.HELD, "sock.json")), "dry run drops nothing")
        code, text = self._cli("held", "prune", "--all")
        self.assertIn("dropped sock", text)
        self.assertIn("dropped gone", text)
        self.assertEqual(sorted(os.listdir(paths.path(paths.HELD))), ["keep.json"])
        self.assertEqual(len(os.listdir(paths.path("legacy-held-originals"))), 2)
        code, text = self._cli("held", "restore", "gone")
        self.assertEqual(code, 0, text)
        self.assertEqual(sorted(os.listdir(paths.path(paths.HELD))), ["gone.json", "keep.json"])
        self.assertEqual(paths.read_json(paths.path(paths.HELD, "gone.json"))["body"], "hello gone")
        code, text = self._cli("held", "restore", "nonesuch")
        self.assertEqual(code, 2, text)

    def test_a_recent_hold_for_a_stopped_session_waits_for_it_to_come_back(self):
        """`claude --resume` brings a stopped session back under the same ref."""
        from xsm import paths
        self._person()
        self._hold("fresh", "ffffff")                          # no record, but held just now
        self._hold("stopped", self.me["ref"], t=time.time() - 3600)   # a stale session, held an hour ago
        code, text = self._cli("held", "prune", "--all")
        self.assertIn("nothing to prune", text)
        self.assertEqual(sorted(os.listdir(paths.path(paths.HELD))), ["fresh.json", "stopped.json"])

    def test_a_socket_mismatch_for_a_live_session_waits_a_day_too(self):
        from xsm import paths, receive
        self._person()
        self._hold("sock", self.you["ref"], reason="from uds:/x, %s 'a'" % receive.SOCKET_MISMATCH)
        code, text = self._cli("held", "prune", "--all")
        self.assertIn("nothing to prune", text)
        self.assertTrue(os.path.exists(paths.path(paths.HELD, "sock.json")))

    def test_an_agent_needs_its_users_yes_to_prune(self):
        from xsm import paths
        self._hold("gone", "ffffff", t=time.time() - self.OLD)
        code, text = self._cli("held", "prune", "--all")
        self.assertEqual(code, 2, text)
        self.assertIn("refused:", text)
        self.assertTrue(os.path.exists(paths.path(paths.HELD, "gone.json")), "nothing dropped unasked")
        code, text = self._cli("held", "prune", "--all", "--dry-run")
        self.assertEqual(code, 0, text)
        self.assertIn("would drop gone", text, "looking costs no yes")

    def test_prune_without_all_leaves_other_sessions_alone(self):
        from xsm import paths
        self._person()
        self._hold("theirs-gone", "ffffff", t=time.time() - self.OLD)
        code, text = self._cli("held", "prune")
        self.assertIn("nothing to prune", text)
        self.assertTrue(os.path.exists(paths.path(paths.HELD, "theirs-gone.json")))

    def test_a_hold_with_no_named_receiver_is_not_listed_as_mine(self):
        from xsm import paths
        paths.write_json(paths.path(paths.HELD, "old.json"), {
            "t": time.time(), "reason": "r", "runtime": "claude", "from": "x", "body": "b"})
        code, text = self._cli("held", "list")
        self.assertNotIn("old", text.split("more held")[0])
        self.assertIn("1 more held for other sessions or with no named receiver", text)
        code, text = self._cli("held", "list", "--all")
        self.assertIn("old", text)


class StoppedReasonsTest(unittest.TestCase):
    def test_each_reason_is_said_in_words_and_never_as_a_raw_code(self):
        from xsm import send
        for why in ("socket_dead", "pid_dead", "lstart_changed", "thread_unloaded", "thread_replaced"):
            text = send.stopped_why({"state_why": why})
            self.assertIn(send.STOPPED_WHY[why], text)
            self.assertIn("registers again with its next prompt", text)
        for why in ("protocol_closed", "worker_stopped", "profile_migrated", "no_pid"):
            text = send.stopped_why({"state_why": why})
            self.assertIn(send.STOPPED_ELSE[why], text)
            self.assertNotIn("registers again", text, "a clean end is not a lost process")
        self.assertIn("another conversation", send.stopped_why({"state_why": "live",
                                                                 "end_reason": "superseded"}))
        odd = send.stopped_why({"state_why": "live"})
        self.assertNotIn("(live)", odd)
        self.assertNotIn("process check failed", odd)


class ReplacedKeepsTheRulesTest(_Sessions):
    def test_a_replaced_answer_that_is_a_yes_still_needs_the_show_and_goes_ahead_once(self):
        from xsm import config
        self._send()
        self._reply("아니")
        self._reply("응, 연결하고 보내")
        code, shown = self._send()
        self.assertEqual(code, 2, shown)
        self.assertIn('replaced their earlier answer "아니"', shown)
        self.assertEqual((self.sent, config.links()), ([], []), "showing is not going ahead")
        self._waited()
        code, passed = self._send()
        self.assertEqual(code, 3, passed)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(config.links()), 1)

    def test_a_long_earlier_answer_is_cut_in_the_note(self):
        self._send()
        self._reply("응 " * 200)
        self._reply("지금 어때?")
        code, shown = self._send()
        quoted = shown.split('replaced their earlier answer "')[1].split('"')[0]
        self.assertLessEqual(len(quoted), 200)


if __name__ == "__main__":
    unittest.main()
