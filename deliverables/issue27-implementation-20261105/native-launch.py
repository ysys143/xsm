"""Actual isolated Claude CLI, existing subscription OAuth scoped to its child.

No keychain/config modification or token output. Control the native terminal;
this wrapper neither answers questions nor edits XSM product state.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
info = json.loads((OUT / 'native-preflight.json').read_text())
root = Path(info['root'])
role = sys.argv[1]
if role not in ('a', 'b'):
    raise SystemExit('select isolated a or b')
home = root / role
secret = subprocess.run(['security', 'find-generic-password', '-s', info['keychain_service'], '-w'],
                        capture_output=True, text=True, timeout=20)
if secret.returncode:
    raise SystemExit('subscription credential is unavailable')
try:
    access = json.loads(secret.stdout)['claudeAiOauth']['accessToken']
except (ValueError, KeyError, TypeError):
    raise SystemExit('existing subscription credential format is unsupported')
if not access:
    raise SystemExit('existing subscription access is unavailable')
env = dict((key, value) for key, value in os.environ.items() if not key.startswith('CLAUDE'))
env.update(CLAUDE_CONFIG_DIR=str(home), XSM_HOME=str(root / 'state'),
           CLAUDE_CODE_OAUTH_TOKEN=access, MAX_THINKING_TOKENS='1000')
for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDECODE',
            'CLAUDE_CODE_SESSION_ID', 'CLAUDE_SESSION_ID', 'CLAUDE_CODE_MESSAGING_SOCKET'):
    env.pop(key, None)
guard = {}
for name in ('.claude', '.claude-2', '.claude-3', '.codex', '.codex-2', '.codex-3'):
    for basename in ('config.toml', 'settings.json', 'hooks.json'):
        path = Path('/Users/jaesolshin') / name / basename
        guard[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
(OUT / ('native-' + role + '-config-before.json')).write_text(json.dumps(guard, indent=2) + '\n')
args = ['claude', '--ax-screen-reader', '--permission-mode', 'default', '--settings', str(home / 'settings.json'), '--setting-sources', 'user',
        '--mcp-config', str(home / 'mcp.json'), '--strict-mcp-config', '--effort', 'low',
        '--session-id' if role == 'a' else '--resume', info['conversation'],
        'Call xsm_inbox once, then reply exactly XSM_PROFILE_' + role.upper() + '_READY. '
        'Do not call other tools or change any files.']
os.chdir(root / 'work')
os.execvpe('script', ['script', '-q', str(OUT / ('native-' + role + '.terminal.log')), *args], env)
