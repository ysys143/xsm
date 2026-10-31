# Shared documents: add nodes, never edit the file

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
