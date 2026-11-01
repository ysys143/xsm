"""Inject decision defects into an isolated server; never imported by the checker."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from xsm import protocol

fault = sys.argv[1]
original = protocol.Connection.decision_response


def response(connection, token, host, params):
    if fault == 'ignore-display':
        item = next((item for item in connection.ui_requests.values()
                     if item['event']['questionId'] == params.get('questionId')), None)
        if item is not None:
            params = dict(params, displayed=item['event']['question'])
    result = original(connection, token, host, params)
    if fault == 'auto-apply':
        connection.dispatch('operation.call', {'session': token, 'operation': 'xsm_decide',
            'arguments': {'question': 'Fixture: choose a color', 'options': ['blue', 'green'],
                          'decision_key': 'wire-first'}})
    return result


protocol.Connection.decision_response = response
protocol.serve()
