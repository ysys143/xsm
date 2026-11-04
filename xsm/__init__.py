"""xsm — cross-session messaging for Claude Code and Codex sessions.

No daemon, no coordinator, no network by default: hooks register pointers,
a one-shot CLI sends over each runtime's own native path, and every piece of
state is a file. See docs/xsm/README.md for supported behavior and setup.
"""

__version__ = "0.6.0"
