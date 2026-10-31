"""Final identifier check over every S12b artifact. Prints counts only, never values.

A hit is (a) a UUID-shaped string within 80 characters after an account/organization/user/email key, or
(b) an e-mail-shaped string anywhere. Board-text names such as 'svc/auth/...' are not identifiers and do not match.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT.parents[1] / 'docs/spikes'
KEY = r'(account_uuid|organization_uuid|accountUuid|organizationUuid|orgId|org_id|userID|user_id|userId|account_id|accountId|email)'
UUID = r'[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}'
NEAR = re.compile(KEY + r'.{0,80}?' + UUID, re.S)
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
KEYONLY = re.compile(r'"' + KEY + r'"')


def main():
    files = [p for p in ROOT.rglob('*') if p.is_file()] + sorted(DOCS.glob('S12b-*'))
    res = dict(files_scanned=len(files), uuid_next_to_account_key=0, email_pattern=0, account_key_names=0, files_with_hits=0)
    for p in files:
        try:
            t = p.read_text(errors='replace')
        except Exception:
            continue
        a, b, c = len(NEAR.findall(t)), len(EMAIL.findall(t)), len(KEYONLY.findall(t))
        res['uuid_next_to_account_key'] += a
        res['email_pattern'] += b
        res['account_key_names'] += c
        res['files_with_hits'] += bool(a or b)
    (ROOT / 'scrub-check.json').write_text(json.dumps(res, indent=2) + '\n')
    print(json.dumps(res))


if __name__ == '__main__':
    main()
