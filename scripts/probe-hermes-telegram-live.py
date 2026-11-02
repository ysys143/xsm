#!/usr/bin/env python3
"""One approved-chat native Telegram transport probe; no model or gateway-agent claims."""
import argparse
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import stat
import subprocess
import sys
import time


def private_text(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('private profile file required')
        return stream.read()


async def run(args):
    profile = args.profile.resolve()
    target = json.loads(private_text(profile / 'test-target.json'))
    entries = []
    for line in private_text(profile / '.env').splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and key == 'HERMES_TELEGRAM_BOT_TOKEN':
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            entries.append(value)
    if len(entries) != 1 or not entries[0]:
        raise ValueError('one nonempty credential required')
    inherited = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    os.environ.clear()
    os.environ.update(inherited, HOME=str(profile / 'runtime-home'), HERMES_HOME=str(profile),
        XSM_HOME=str(profile / 'xsm-state'), TELEGRAM_BOT_TOKEN=entries[0],
        TELEGRAM_ALLOWED_USERS=str(target['user_id']), PYTHONDONTWRITEBYTECODE='1')
    os.chdir(profile / 'runtime-home')
    sys.path.insert(0, str(args.native_source.resolve()))
    # HTTP client logs can include credential-bearing Bot API URLs.
    logging.disable(logging.CRITICAL)
    from gateway.config import PlatformConfig
    from plugins.platforms.telegram.adapter import TelegramAdapter
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token=entries[0], typing_indicator=False,
        gateway_restart_notification=False, extra={'drop_pending_on_cold_boot': False, 'status_indicator': False}))
    received = asyncio.Event()
    report = {'scope': 'real native Telegram adapter and approved private chat only',
              'model_calls': 0, 'gateway_agent_runner': False, 'xsm_delivery_verified': False,
              'started_at': time.time(), 'target_fingerprint': hashlib.sha256(str(target['chat_id']).encode()).hexdigest()[:12]}
    async def incoming(event):
        if (str(event.source.chat_id) == str(target['chat_id'])
                and str(event.source.user_id) == str(target['user_id'])
                and event.text == '/start ' + target['confirmation_nonce']):
            report['native_inbound_confirmed'] = True
            report['native_source_chat_type'] = event.source.chat_type
            received.set()
        return None
    adapter.set_message_handler(incoming)
    try:
        connected = await asyncio.wait_for(adapter.connect(), 45)
        report['native_connected'] = connected
        if not connected:
            raise RuntimeError('native connection failed')
        await asyncio.wait_for(received.wait(), 30)
        # One explicit, fixed diagnostic response to the user-designated chat.
        result = await asyncio.wait_for(adapter.send(str(target['chat_id']),
            'XSM Hermes Telegram transport probe: receive and send confirmed (6e314b92). No model reply yet.'), 20)
        report['native_send_confirmed'] = bool(result.success)
        report['sent_message_count'] = 1 if result.success else 0
        if not result.success:
            raise RuntimeError('native send not confirmed')
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', failure_type=type(error).__name__)
    finally:
        try:
            await asyncio.wait_for(adapter.disconnect(), 20)
            report['native_disconnected'] = True
        except BaseException as error:
            report.update(status='failed', disconnect_failure_type=type(error).__name__)
        report['finished_at'] = time.time()
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--native-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.absolute()
    if args.output.exists():
        parser.error('output must be new; preserve previous evidence')
    actual = subprocess.check_output(['git', '-C', str(args.native_source), 'rev-parse', 'HEAD'], text=True).strip()
    tagged = subprocess.check_output(['git', '-C', str(args.native_source), 'rev-parse', 'v0.22.5^{}'], text=True).strip()
    if actual != tagged:
        parser.error('the pinned v0.22.5 checkout is required')
    return asyncio.run(run(args))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'failed', 'failure_type': type(error).__name__}))
        raise SystemExit(1) from None
