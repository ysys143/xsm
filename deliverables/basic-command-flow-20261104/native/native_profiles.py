"""Fresh native profiles only; all inference uses the existing bounded OAuth relay."""
import json
import secrets
import socket


def configure(args, root, relay):
    profile = root / args.runtime
    profile.mkdir(mode=0o700)
    base = 'http://127.0.0.1:' + str(relay.server.server_port) + '/v1'
    if args.runtime == 'hermes':
        config = {
            'model': {'default': args.model, 'provider': 'custom', 'base_url': base,
                      'api_key': 'local-proxy-placeholder', 'api_mode': 'chat_completions'},
            'fallback_providers': [],
            'agent': {'max_turns': 6, 'max_tokens': 1000, 'skip_context_files': True,
                      'api_max_retries': 1, 'auto_recovery_cycles': 0,
                      'background_review': {'enabled': False}},
            'memory': {'enabled': False}, 'plugins': {'enabled': ['xsm']}, 'toolsets': ['xsm'],
            'gateway': {'standalone': True, 'multiplex_profiles': False,
                        'unmanaged_idle_exit_seconds': 5},
            'terminal': {'cwd': str(root / 'workspace')},
        }
        filename = profile / 'config.yaml'
        model = args.model
    elif args.runtime == 'openclaw':
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        model = 'xsm-subscription/' + args.model
        config = {
            'gateway': {'mode': 'local', 'bind': 'loopback', 'port': port,
                        'auth': {'mode': 'token', 'token': secrets.token_hex(32)}},
            'agents': {'defaults': {'workspace': str(root / 'workspace'),
                                   'heartbeat': {'every': '0m'},
                                   'model': {'primary': model, 'fallbacks': []}}},
            'cron': {'enabled': False},
            'plugins': {'enabled': True, 'allow': ['xsm'], 'entries': {'xsm': {'enabled': True}}},
            'models': {'providers': {'xsm-subscription': {
                'api': 'openai-completions', 'baseUrl': base, 'apiKey': 'local-proxy-placeholder',
                'agentRuntime': {'id': 'openclaw'}, 'models': [{
                    'id': args.model, 'name': args.model, 'reasoning': False, 'input': ['text'],
                    'contextWindow': 200000, 'maxTokens': 1000}]}}},
        }
        filename = profile / 'openclaw.json'
    else:
        raise ValueError('unsupported fresh native profile')
    filename.write_text(json.dumps(config, indent=2) + '\n')
    filename.chmod(0o600)
    return profile, model
