---
type: llm
weight: 1
---

A good answer uses xsm's opt-in P2P network: create one on one Mac
(`xsm network init`), issue an invitation (`xsm network invite`, which writes a
private file), move that file to the other Mac through a private channel the
user chooses, and join there (`xsm network join --ticket-file ...`). It then
finds the remote session with `xsm discover` (or `xsm_discover`), lets the user
pick one, and connects or asks with the returned target.

It is wrong if it says SSH is required, invents commands or flags that are not
xsm's, tells the user to paste the invitation's contents into a chat or a
command line, or treats joining the network as permission to collaborate with
every session on it.
