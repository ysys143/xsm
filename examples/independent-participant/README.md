# Independent-input Python host participant

Python standard library only. Trusted operators select the server executable and public checker; no personal checkout path or bundled input/result location is built into the example.

```sh
python3 -B examples/independent-participant/verify.py \
  --server-executable /absolute/path/to/xsm \
  --checker /absolute/path/to/conform-host-protocol.py \
  --output ./participant-evidence-new

python3 -B examples/independent-participant/participant.py \
  --server-executable /absolute/path/to/xsm --conversation cli-fixture

python3 -B examples/independent-participant/transport_fixtures.py \
  --output ./transport-evidence-new.json
```

`verify.py` requires a new output directory and refuses an existing one. The mock fixture report uses exclusive creation too. Use `-B` to avoid bytecode writes beside an operator-selected checker. `--checker` loads Python code and is a trusted operator input, not an untrusted document attachment.

`--server-executable` must be absolute. `server_command` appends only the fixed `protocol serve --stdio` argv. There is no shell. `Peer(command, ...)` is a host/operator API, not a model-facing tool. CLI JSON request content and peer messages cannot change the child executable or its argv. Run an operator-selected executable only within the operator's authorization.

The CLI emits initialization/session information, then accepts one local JSON request per line. Use `"session":"$session"` for the opened opaque handle. `{"method":"$notification"}` waits for one host notification. Responses are local `result`/`error` envelopes. EOF closes and reaps the server. No automatic ACK or decision answer is performed.

```json
{"method":"operation.call","params":{"session":"$session","operation":"xsm_inbox","arguments":{}}}
```

`Peer.submit` returns a Future; multiple requests may be outstanding. One reader correlates responses by ID and queues notifications independently. `call` has a five-second observation deadline. Reader or write failure becomes terminal: pending requests fail and later submissions raise the stored failure immediately, even while the child is still alive. Close still needs to be called to reap it. `close` attempts stdin closure, fallback closure of a still-open raw stream/descriptor, wait/kill/reap, stdout/stderr closure and temporary-directory cleanup. Cleanup errors are returned in diagnostics rather than silently claiming success.

Wire bytes are explicitly decoded as strict UTF-8 before JSON parsing. NaN/Infinity/-Infinity are rejected on input and output. The parser also refuses floating-point overflow such as `1e400`; that is this participant's finite-native-number restriction, not a claim that the public JSON contract universally prohibits that valid numeric spelling.

Sessions and claim tokens stay opaque. The generic request API forwards negotiated methods (the current catalog contains 16); `operation` preserves structured/text result envelopes without parsing display prose. Reconnect is explicit: close the old peer, create a new one with the same isolated directory, initialize and reopen the same profile/conversation. Never transfer an old handle/token. `open` is a fixture convenience; use `call('session.open', ...)` for custom profile/capabilities.

`fixture_answer` is a synthetic display/callback fixture: it copies that event's exact question, question ID, challenge and session. It is not a native UI or evidence of human approval. `abandon` releases that display route without answering. Real applications need their own presentation/callback integration. Private challenges must not enter model tools or peer messages. Local wire reports intentionally contain temporary fixture handles.

Every child uses the caller-provided isolated fixture directory or a newly created temporary directory for cwd/HOME/XSM_HOME. Only PATH/LANG/TMPDIR are inherited. This environment filtering is not an OS sandbox or independent proof that an arbitrary operator-selected executable cannot access the network/filesystem. Message display text is untrusted data and is never executed.

The verification module reuses the selected public stdlib checker's scenarios with this newly authored transport, then runs extra fixtures. Mock transport tests use no child processes and inject four defects into in-memory copies of this participant to verify the regression checks actually reject them. Successful mock results do not certify the actual server's handling of malformed frames.

Local limits include a 4 MiB output-frame byte guard, five-second RPC observation deadline, integer outgoing request IDs, and finite floating-point parsing. Full operation-result schemas, attachment identifier extraction/fallback negotiation, wake value semantics and complete decision lifecycle semantics remain contract gaps in the supplied input. Prior result reports distinguish those gaps from completed fixtures. Input/implementation separation is evidence, not certification of cognitive independence.
