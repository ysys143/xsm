"""Opt-in attention requests. OS-call success never means a human saw it."""
from __future__ import annotations

import subprocess
import time

from . import decisions, paths


def notify(key, title, body, enabled=False, interval=60, runner=None):
    decisions.filename(key)  # validate an opaque decision key, never a path
    if not isinstance(title, str) or not isinstance(body, str):
        raise ValueError("notification title and body must be text")
    state = paths.read_json(paths.path("attention", key + ".json"), {})
    now = time.time()
    request = {"id": key, "requested_at": now, "human_saw": None,
               "title": title, "body_digest": decisions.digest(body),
               "requested_chars": len(body), "observed_display_range": None}
    if not enabled:
        request.update(status="suppressed", reason="disabled")
    elif state.get("os_called_at") is not None and now - state["os_called_at"] < interval:
        request.update(status="suppressed", reason="frequency")
    else:
        # argv avoids interpolation of untrusted text into AppleScript code.
        script = ('on run argv\n display notification (item 2 of argv) with title '
                  '(item 1 of argv)\nend run')
        request.update(status="requested", os_called_at=now)
        paths.write_json(paths.path("attention", key + ".json"), request)
        try:
            call = runner or subprocess.run
            result = call(["osascript", "-e", script, title, body], capture_output=True,
                          text=True, timeout=5)
            request.update(status="os-call-succeeded" if result.returncode == 0 else "failed",
                           exit_code=result.returncode)
        except (OSError, subprocess.TimeoutExpired) as exc:
            request.update(status="failed", reason=type(exc).__name__)
    if state.get("os_called_at") is not None and "os_called_at" not in request:
        request["os_called_at"] = state["os_called_at"]
    paths.write_json(paths.path("attention", key + ".json"), request)
    return request
