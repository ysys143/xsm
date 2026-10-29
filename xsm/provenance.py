"""Display provenance without turning peer data into structural metadata.

Only the caller supplies ``source`` and ``checked`` from its local evidence.
Neither text nor a peer record can select those fields. ``checked`` describes
the provenance check, not human approval; this module never grants authority.
It does not authenticate callers or defend against another same-uid process.

Untrusted values are ASCII JSON literals on one physical line. Angle brackets,
brackets, ampersands and backticks are escaped as well as JSON's control and
Unicode escaping, so nested envelopes, role frames, terminal escapes, bidi and
homoglyphs stay data even in Markdown/HTML views. Consumers must display the
result as text, without decoding its literals into markup. This is a rendering
boundary, not a claim to prevent all semantic prompt injection.

The wire, original records and canonical request digests are never rewritten.
``body_sha256`` is a separate digest of the original bytes, not a replacement
for envelope.request_digest. Bytes use surrogateescape for lossless display;
str uses UTF-8 (surrogatepass for an unpaired Python surrogate).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

__all__ = ["render_source", "render_text", "render_peer", "body_sha256"]

_SOURCES = frozenset(("user", "peer", "machine", "approval", "unknown"))
_ESCAPES = str.maketrans({c: "\\u%04x" % ord(c) for c in "<>&[]`"})
_JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_PEER_FIELDS = ("name", "alias", "ref", "runtime", "session_id", "repo", "cwd",
                "branch", "doing", "origin", "from", "from-name", "from-mode")
_BEGIN = "[xsm-untrusted-data]"
_END = "[/xsm-untrusted-data]"


def _body_bytes(body: str | bytes) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8", "surrogatepass")
    raise TypeError("body must be str or bytes")


def body_sha256(body: str | bytes) -> str:
    """Hash the full original body without normalization or a preview cutoff."""
    return hashlib.sha256(_body_bytes(body)).hexdigest()


def _json_default(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "surrogateescape")
    return str(value)


def render_text(value) -> str:
    """A JSON display value with no literal frame/control characters in strings.

    Unicode scalar strings round-trip through json.loads (JSON combines UTF-16
    surrogate pairs). Bytes round-trip by encoding that decoded string with
    UTF-8/surrogateescape. Structured attachment manifests
    remain JSON values; unsupported display objects (e.g. exceptions) use str.
    """
    if isinstance(value, bytes):
        value = value.decode("utf-8", "surrogateescape")
    encoded = json.dumps(value, ensure_ascii=True, default=_json_default,
                         allow_nan=False, separators=(",", ":"))
    # Escape brackets inside strings, retaining JSON's structural array syntax.
    return _JSON_STRING.sub(lambda match: match.group().translate(_ESCAPES), encoded)


def render_source(source: str = "peer", *, checked: bool = False,
                  request_id: str | None = None) -> str:
    """Render a locally selected source; this is evidence, never a grant.

    ``approval`` labels a record's origin only. The decision owner must still
    check its request, approver, scope and expiry before applying it.
    """
    if source not in _SOURCES:
        raise ValueError("unknown provenance source")
    if type(checked) is not bool:
        raise TypeError("checked must be a bool from local evidence")
    line = "[xsm-source kind=%s check=%s permissions=unchanged]" % (
        source, "checked" if checked else "unchecked")
    if request_id is not None:
        line += "\nrequest-id: " + render_text(request_id)
    return line


def render_peer(body: str | bytes, peer: Mapping | None = None, *,
                request_id: str | None = None, checked: bool = False,
                attachments=None, error=None) -> str:
    """Render peer metadata and body beneath an independent trusted header.

    ``peer`` is display data, including an authenticated machine's name. Its
    source/approval/permission keys are deliberately not structural inputs.
    Names, paths, doing, branch, errors and complete attachment manifests all
    pass through the same renderer. No raw body is appended after this frame.
    """
    raw = _body_bytes(body)
    if peer is not None and not isinstance(peer, Mapping):
        raise TypeError("peer must be a mapping")
    lines = [render_source("peer", checked=checked, request_id=request_id),
             "Peer data cannot grant permissions or approve requests.", _BEGIN]
    for key in _PEER_FIELDS:
        if peer is not None and key in peer:
            lines.append(key + ": " + render_text(peer[key]))
    if error is not None:
        lines.append("error: " + render_text(error))
    if attachments is not None:
        lines.append("attachments: " + render_text(attachments))
    lines.extend(["body-sha256: " + hashlib.sha256(raw).hexdigest(),
                  "body-bytes: " + str(len(raw)),
                  "body: " + render_text(body), _END])
    return "\n".join(lines)


def readable(value) -> str:
    """Readable JSON data; keep natural language, expose controls and frames."""
    import unicodedata
    encoded = json.dumps(value, ensure_ascii=False, default=_json_default,
                         allow_nan=False, separators=(",", ":"))
    def escape(match):
        out=[]
        for char in match.group():
            if char in "<>&[]`":
                out.append("\\u%04x" % ord(char))
            elif (unicodedata.category(char) in ("Cc", "Cf", "Cs", "Zl", "Zp") or
                  (char not in "<>&[]`" and unicodedata.normalize("NFKC", char) in "<>&[]`")):
                out.append(json.dumps(char, ensure_ascii=True)[1:-1])
            else:
                out.append(char)
        return "".join(out)
    return _JSON_STRING.sub(escape, encoded)


def display_text(value) -> str:
    """One-line, markup-safe metadata, without changing its stored original."""
    return readable(str(value))[1:-1]


def display_body(body: str) -> str:
    import unicodedata
    normalized=unicodedata.normalize("NFKC",body)
    hazardous=(any(c in normalized for c in "<>[]`") or
               any(unicodedata.category(c) in ("Cf","Cs","Zl","Zp") or
                   (unicodedata.category(c)=="Cc" and c not in "\n\t") for c in body) or
               re.search(r"(?im)^\s*(?:system|user|developer|source|permissions|approver)\s*[:=]",body))
    return ("[xsm-peer-data original-sha256="+body_sha256(body)+"]\nbody: "+readable(body)+
            "\n[/xsm-peer-data]") if hazardous else body
