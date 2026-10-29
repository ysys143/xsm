#!/usr/bin/env python3
"""Summarize direct replies in a UTF-8 JSONL message log."""

import argparse
import json
import sys


class InvalidInput(ValueError):
    pass


def invalid_constant(value):
    raise ValueError("invalid JSON constant: " + value)


def summarize(stream):
    records = {}
    for line_number, raw_line in enumerate(stream, 1):
        try:
            line = raw_line.decode("utf-8")
            if not line.strip():
                continue
            record = json.loads(line, parse_constant=invalid_constant)
            if not isinstance(record, dict):
                raise ValueError("record must be an object")
            message_id = record.get("id")
            if not isinstance(message_id, str) or not message_id:
                raise ValueError("id must be a nonempty string")
            target = record.get("reply_to")
            if target is not None and (not isinstance(target, str) or not target):
                raise ValueError("reply_to must be null or a nonempty string")
            if message_id in records and records[message_id] != target:
                raise ValueError("conflicting reply_to for duplicate id")
            records[message_id] = target
        except (ValueError, UnicodeError) as error:
            raise InvalidInput(f"line {line_number}: {error}") from error

    roots = {message_id for message_id, target in records.items() if target is None}
    targets = {target for target in records.values() if target is not None}
    return {
        "request_count": len(roots),
        "answered": sorted(roots & targets),
        "unanswered": sorted(roots - targets),
        "orphan_replies": sorted(
            message_id for message_id, target in records.items()
            if target is not None and target not in records
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="UTF-8 JSONL file, or - for stdin")
    parser.add_argument("--fail-on-unanswered", action="store_true",
                        help="exit 3 if valid input contains unanswered requests")
    args = parser.parse_args()
    try:
        if args.input == "-":
            result = summarize(sys.stdin.buffer)
        else:
            with open(args.input, "rb") as stream:
                result = summarize(stream)
    except (InvalidInput, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 3 if args.fail_on_unanswered and result["unanswered"] else 0


if __name__ == "__main__":
    sys.exit(main())
