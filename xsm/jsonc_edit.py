"""Position-preserving JSONC edits. Never serialize unrelated user settings."""
from __future__ import annotations

import json


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSONC key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("invalid JSONC constant: " + value)


class Document:
    def __init__(self, text):
        self.text = text
        clean = list(text)
        if clean and clean[0] == "\ufeff":
            clean[0] = " "
        i, quoted = 0, False
        while i < len(text):
            char = text[i]
            if quoted:
                if char == "\\":
                    i += 2
                    continue
                if char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif text[i:i + 2] in ("//", "/*"):
                end = text.find("\n", i + 2) if text[i:i + 2] == "//" else text.find("*/", i + 2)
                if end < 0:
                    if text[i:i + 2] == "/*":
                        raise ValueError("unterminated JSONC comment")
                    end = len(text)
                elif text[i:i + 2] == "/*":
                    end += 2
                clean[i:end] = [c if c in "\r\n" else " " for c in text[i:end]]
                i = end
                continue
            i += 1
        self.comments_removed = "".join(clean)
        i, quoted = 0, False
        while i < len(clean):
            char = clean[i]
            if quoted:
                if char == "\\":
                    i += 2
                    continue
                if char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char == ",":
                end = i + 1
                while end < len(clean) and clean[end].isspace():
                    end += 1
                if end < len(clean) and clean[end] in "]}":
                    clean[i] = " "
            i += 1
        self.normalized = "".join(clean)
        self.decoder = json.JSONDecoder(object_pairs_hook=_unique, parse_constant=_constant)
        self.value = self.decoder.decode(self.normalized)
        if not isinstance(self.value, dict):
            raise ValueError("native config must be a JSONC object")
        self.members = {}
        pos = self.space(self.normalized.index("{") + 1)
        while self.normalized[pos] != "}":
            key, end = self.decoder.raw_decode(self.normalized, pos)
            start = self.space(self.space(end) + 1)
            value, stop = self.decoder.raw_decode(self.normalized, start)
            self.members[key] = (start, stop, value)
            pos = self.space(stop)
            if self.normalized[pos] == ",":
                pos = self.space(pos + 1)

    def space(self, pos):
        while pos < len(self.normalized) and self.normalized[pos].isspace():
            pos += 1
        return pos

    def plugins(self):
        if "plugin" not in self.members:
            return []
        start, end, value = self.members["plugin"]
        if not isinstance(value, list):
            raise ValueError("native plugin setting must be an array")
        items, pos = [], self.space(start + 1)
        while pos < end - 1:
            item, stop = self.decoder.raw_decode(self.normalized, pos)
            if not (isinstance(item, str) or (isinstance(item, list) and len(item) == 2 and
                    isinstance(item[0], str) and isinstance(item[1], dict))):
                raise ValueError("invalid native plugin entry")
            items.append((pos, stop, item))
            pos = self.space(stop)
            if self.normalized[pos] == ",":
                pos = self.space(pos + 1)
        return items

    def insert(self, uri):
        literal = json.dumps(uri, ensure_ascii=False)
        items = self.plugins()
        if "plugin" not in self.members:
            pos = self.normalized.index("{") + 1
            fragment = '"plugin": [' + literal + ']' + ("," if self.value else "")
        elif items:
            pos = items[-1][1]
            fragment = ", " + literal
        else:
            pos = self.members["plugin"][0] + 1
            fragment = literal
        edited = self.text[:pos] + fragment + self.text[pos:]
        Document(edited)
        return edited, fragment

    def replace(self, index, uri):
        start, end, item = self.plugins()[index]
        if not isinstance(item, str):
            raise ValueError("edited native xsm plugin options preserved")
        return self.text[:start] + json.dumps(uri, ensure_ascii=False) + self.text[end:]

    def remove(self, index):
        items = self.plugins()
        start, end, _ = items[index]
        edits = [(start, end)]
        if index:
            comma = self.comments_removed.index(",", items[index - 1][1], start)
            edits.append((comma, comma + 1))
        else:
            limit = items[index + 1][0] if len(items) > 1 else self.members["plugin"][1] - 1
            comma = self.comments_removed.find(",", end, limit)
            if comma >= 0:
                edits.append((comma, comma + 1))
        edited = self.text
        for left, right in sorted(edits, reverse=True):
            edited = edited[:left] + edited[right:]
        Document(edited)
        return edited
