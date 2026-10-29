# The channel and shared documents

## The channel: the record you keep with your user and other sessions

```bash
xsm post "Benchmark: kafka 2x faster" --tag result      # or the xsm_post MCP tool
xsm channel show [--tag decision]                       # or xsm_channel
```

Posting records; it wakes nobody (use `xsm send` to call a session). Tags:
note, question, proposal, result, hypothesis, decision. Reply with
`--reply-to <id>` to keep a thread.

**A decision is your user's, not yours.** You cannot post one. When a choice
should be on record, call the `xsm_decide` MCP tool with the question and the
options: your user sees a form and picks; their answer is recorded with the
question. Do not phrase your own proposal as a decision — post it as
`proposal` and ask.

In a sandboxed Codex, use the MCP tools: the shell cannot write the channel.

## Shared documents: add nodes, never edit the file

`xsm doc next <doc>` lists what is open: the nodes nothing builds on, plus the
hypotheses nobody has verified. It is a list of facts, not a ranking and not an
assignment — xsm does not decide who does what. Pick one, then say so with
`xsm doc add <doc> --tag wip --parent <id>` so the others can see it is taken.

A research document written by several sessions is a set of immutable nodes
(`xsm doc add <doc> --tag result|insight|hypothesis|verification|report
--text … [--parent <id>]`); the document is rendered from them (`xsm doc
render <doc>`). Do not edit the rendered file or another session's node — to
revise, add a node with `--parent`. `endorsed` is your user's: ask with the
`xsm_doc_endorse` MCP tool.
