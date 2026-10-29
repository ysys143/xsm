"""Native Claude event arrays: selected protocol fields only, no private body."""
import json
import os
import uuid

from tests import test_xsm

SESSION = '12345678-1234-4234-8234-123456789abc'
ACTUAL_LOG = '/tmp/b04-opus-review.json'


class NativeEventsTest(test_xsm.TempState):
    def _parse(self, events):
        from xsm import workers
        return workers._owned_native_result({'runtime': 'claude'},
                    {'native_session_id': None, 'session_seed': SESSION}, json.dumps(events))

    def _final(self, **changes):
        value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                 'session_id': SESSION, 'result': 'selected final body', 'permission_denials': []}
        value.update(changes)
        return value

    def test_array_selects_actual_single_terminal_result(self):
        events = [{'type': 'system', 'session_id': SESSION},
                  {'type': 'assistant', 'session_id': SESSION, 'message': 'not a final answer'},
                  self._final(permission_denials=[{}, {}])]
        result = self._parse(events)
        self.assertEqual(result['body'], 'selected final body')
        self.assertIsNone(result['outcome'])
        self.assertEqual(result['native_evidence']['permission_denial_count'], 2)
        self.assertEqual(result['native_evidence']['event_count'], 3)

    def test_sanitized_498_event_actual_shape_regression(self):
        # Whitelisted summary of the supplied real log: no original bodies,
        # tool inputs, keys, names or actual session values are retained here.
        counts = {'system': 296, 'assistant': 124, 'user': 75, 'rate_limit_event': 2}
        events = [{'type': kind, 'session_id': SESSION} for kind, count in counts.items()
                  for _ in range(count)]
        events.append(self._final(permission_denials=[{}, {}]))
        self.assertEqual(len(events), 498)
        result = self._parse(events)
        self.assertEqual(result['body'], 'selected final body')
        self.assertEqual(result['native_evidence']['event_count'], 498)

    def test_terminal_errors_duplicate_final_other_session_and_unfinished_rejected(self):
        from xsm import workers
        invalid = [[self._final(is_error=True)],
                   [self._final(subtype='error_during_execution')],
                   [self._final(), self._final()],
                   [{'type': 'error', 'session_id': SESSION}, self._final()],
                   [{'type': 'system', 'session_id': str(uuid.uuid4())}, self._final()],
                   [self._final(session_id=str(uuid.uuid4()))],
                   [{'type': 'assistant', 'session_id': SESSION}],
                   [self._final(), {'type': 'assistant', 'session_id': SESSION}],
                   [None, self._final()]]
        for events in invalid:
            with self.subTest(case=invalid.index(events)):
                with self.assertRaises(workers.WorkerError):
                    self._parse(events)

    def test_single_dict_remains_supported(self):
        self.assertEqual(self._parse(self._final())['body'], 'selected final body')

    def test_supplied_actual_log_selected_protocol_fields_only(self):
        if not os.path.exists(ACTUAL_LOG):
            self.skipTest('coordinator private native log is local-only')
        with open(ACTUAL_LOG) as stream:
            original = json.load(stream)
        self.assertIsInstance(original, list)
        final = [r for r in original if isinstance(r, dict) and r.get('type') == 'result']
        self.assertEqual(len(final), 1)
        actual_session = final[0].get('session_id')
        # Never pass the original result/tool message to assertions or parser.
        selected = []
        for event in original:
            row = {key: event[key] for key in ('type', 'subtype', 'is_error') if key in event}
            if event.get('session_id'):
                row['session_id'] = SESSION if event['session_id'] == actual_session else str(uuid.uuid4())
            if event.get('type') == 'result':
                row['result'] = 'redacted actual final'
                row['permission_denials'] = [{} for _ in event.get('permission_denials', [])]
            selected.append(row)
        result = self._parse(selected)
        self.assertEqual(result['body'], 'redacted actual final')
        self.assertEqual(result['native_evidence']['event_count'], len(original))


class CodexNativeEventsTest(test_xsm.TempState):
    def _parse(self, events):
        from xsm import workers
        return workers._owned_native_result({'runtime': 'codex'},
                    {'native_session_id': SESSION, 'session_seed': SESSION},
                    '\n'.join(json.dumps(event) for event in events))

    def _trace(self):
        # Selected event structure observed in all three capacity failures.
        # Diagnostic wording is deliberately unrelated to the real response.
        return [{'type': 'thread.started', 'thread_id': SESSION},
                {'type': 'turn.started'},
                {'type': 'error', 'message': 'temporary transport diagnostic'},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'intermediate'}},
                {'type': 'item.started', 'item': {'type': 'command_execution'}},
                {'type': 'item.completed', 'item': {'type': 'command_execution'}},
                {'type': 'item.started', 'item': {'type': 'command_execution'}},
                {'type': 'item.completed', 'item': {'type': 'command_execution'}},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'recovered final'}},
                {'type': 'turn.completed'}]

    def test_recovered_diagnostic_before_native_terminal_completion_is_answer(self):
        result = self._parse(self._trace())
        self.assertEqual(result['body'], 'recovered final')
        self.assertEqual(result['native_session_id'], SESSION)
        self.assertIsNone(result['outcome'])
        self.assertEqual(result['native_evidence']['diagnostic_error_count'], 1)
        self.assertEqual(result['native_evidence']['terminal_event'], 'turn.completed')

    def test_terminal_failed_unfinished_and_error_after_completion_stay_rejected(self):
        from xsm import workers
        invalid = [self._trace()[:-1],
                   self._trace()[:-1] + [{'type': 'turn.failed'}],
                   self._trace() + [{'type': 'error', 'message': 'unrecovered trailing diagnostic'}],
                   self._trace() + [{'type': 'turn.started'}],
                   self._trace()[:-1] + [{'type': 'turn.failed'}, {'type': 'turn.completed'}]]
        for i, events in enumerate(invalid):
            with self.subTest(case=i):
                with self.assertRaises(workers.WorkerError):
                    self._parse(events)

    def test_actual_capacity_logs_use_only_selected_event_structure(self):
        root = '/private/tmp/p08-native-memory-cn0y8j6u/state/owned-requests'
        if not os.path.isdir(root):
            self.skipTest('coordinator private capacity fixture is local-only')
        wanted = {'capacity-3879b3ac-0', 'capacity-3879b3ac-1', 'capacity-3879b3ac-3'}
        tested = set()
        for filename in os.listdir(root):
            if not filename.endswith('.json'):
                continue
            with open(os.path.join(root, filename)) as stream:
                state = json.load(stream)
            for request_id, request in state.get('requests', {}).items():
                if request_id not in wanted:
                    continue
                selected = []
                with open(request['child']['stdout']) as stream:
                    for line in stream:
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        row = {'type': event.get('type')}
                        if event.get('type') == 'thread.started':
                            row['thread_id'] = SESSION  # actual native ID never copied
                        if event.get('type') == 'item.completed':
                            item = event.get('item') or {}
                            row['item'] = {'type': item.get('type')}
                            if item.get('type') == 'agent_message':
                                row['item']['text'] = 'redacted actual answer'
                        if event.get('type') == 'error':
                            row['message'] = 'redacted diagnostic'
                        selected.append(row)
                result = self._parse(selected)
                self.assertEqual(result['body'], 'redacted actual answer')
                self.assertGreater(result['native_evidence']['diagnostic_error_count'], 0)
                tested.add(request_id)
        self.assertEqual(tested, wanted)
