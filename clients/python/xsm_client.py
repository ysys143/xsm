"""Dependency-free asyncio client for the xsm v1 stdio JSON-RPC protocol."""

from __future__ import annotations

import asyncio
import base64
import codecs
import json
import math
import hashlib
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any


class TransportError(Exception):
    """The peer exited, closed stdout, or sent an invalid RPC frame."""


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


class XsmClient:
    """Create with ``await XsmClient.connect()``; always ``await close()``.

    All session methods take the opaque handle returned by session_open.
    Incoming notifications are retrieved with next_notification(). Stderr is
    drained separately into on_stderr (sys.stderr.write by default).
    """

    DEFAULT_COMMAND = ("python3", "-m", "xsm", "protocol", "serve", "--stdio")

    def __init__(self, process, on_stderr, close_timeout):
        self.process = process
        self.initialization = None
        self._on_stderr = on_stderr
        self._close_timeout = close_timeout
        self._pending = {}
        self._sequence = 0
        self._failure = None
        self._close_task = None
        self._notifications = asyncio.Queue()
        self._write_lock = asyncio.Lock()
        self._reader = asyncio.create_task(self._read_stdout())
        self._stderr_reader = asyncio.create_task(self._read_stderr())

    @classmethod
    async def connect(
        cls,
        command: Sequence[str] = DEFAULT_COMMAND,
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        on_stderr: Callable[[str], Any] | None = None,
        close_timeout: float = 1.0,
        initialize_timeout: float = 10.0,
    ):
        if not command or close_timeout <= 0:
            raise ValueError("command must be nonempty and close_timeout positive")
        try:
            valid_timeout = type(initialize_timeout) in (int, float) and math.isfinite(initialize_timeout) and initialize_timeout > 0
        except OverflowError:
            valid_timeout = False
        if not valid_timeout:
            raise ValueError("initialize_timeout must be finite and positive")
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=cwd, env=env,
        )
        client = cls(process, on_stderr or sys.stderr.write, close_timeout)
        try:
            try:
                client.initialization = await asyncio.wait_for(client.request(
                    "initialize", {"protocolVersion": "1"}
                ), initialize_timeout)
            except asyncio.TimeoutError as error:
                raise TransportError("initialize negotiation timed out") from error
            if not isinstance(client.initialization, dict) or client.initialization.get("protocolVersion") != "1":
                raise TransportError("unsupported or malformed protocol version negotiation")
            return client
        except BaseException:
            try:
                await client.close()
            except Exception as cleanup_error:
                try:
                    client._on_stderr("xsm cleanup: " + str(cleanup_error) + "\n")
                except Exception:
                    pass
            raise

    async def request(self, method: str, params: dict | None = None) -> Any:
        """Send an RPC request. Caller cancellation forgets its correlation ID.

        decision.response is deliberately unavailable, including through this
        generic entry point: these clients do not establish host trust.
        """
        if method in ("decision.response", "decision.abandon"):
            raise PermissionError("decision.response requires a trusted host client")
        return await self._request(method, params)

    async def _request(self, method, params=None):
        if not isinstance(method, str) or not method:
            raise ValueError("method must be a nonempty string")
        if params is not None and not isinstance(params, dict):
            raise TypeError("params must be an object")
        if ((method.startswith("session.") and method != "session.open") or method in (
            "operation.call", "events.subscribe", "delivery.report"
        )):
            self._session((params or {}).get("session"))
        if self._failure:
            raise self._failure
        self._sequence += 1
        ident = str(self._sequence)
        # Serialize before registering a future so bad caller data cannot strand it.
        frame = (json.dumps({"jsonrpc": "2.0", "id": ident, "method": method,
                             "params": {} if params is None else params},
                            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        future = asyncio.get_running_loop().create_future()
        self._pending[ident] = future
        try:
            async with self._write_lock:
                if not self._failure:
                    try:
                        self.process.stdin.write(frame)
                        await self.process.stdin.drain()
                    except (OSError, RuntimeError) as exc:
                        self._fail(TransportError(f"stdin write failed: {exc}"))
            return await future
        finally:
            self._pending.pop(ident, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()  # Also consume a failure racing caller cancellation.

    @staticmethod
    def _session(session):
        if not isinstance(session, str) or not session:
            raise ValueError("session must be a nonempty opaque handle")
        return session

    async def session_open(self, *, runtime: str, profile: str,
                           conversation: str, cwd: str,
                           capabilities: Sequence[str] = (), parent_conversation=None) -> dict:
        fields = {
            "runtime": runtime, "profile": profile, "conversation": conversation,
            "cwd": cwd, "capabilities": list(capabilities),
        }
        if parent_conversation is not None:
            if 'native-lineage' not in self.initialization.get('capabilities', []):
                raise TransportError('server does not support native parent lineage')
            fields['parent_conversation'] = parent_conversation
            if 'native-lineage' not in fields['capabilities']:
                fields['capabilities'].append('native-lineage')
        result = await self.request("session.open", fields)
        if (not isinstance(result, dict) or not isinstance(result.get("session"), str)
                or not result["session"] or "generation" not in result):
            error = TransportError("session.open must return session and generation")
            self._fail(error)
            raise error
        return result

    async def session_update(self, session: str, updates: dict) -> Any:
        self._session(session)
        if not isinstance(updates, dict) or "session" in updates:
            raise ValueError("updates must be an object without session")
        return await self.request("session.update", {**updates, "session": session})

    async def session_close(self, session: str) -> Any:
        return await self.request("session.close", {"session": self._session(session)})

    async def operation_call(self, session: str, operation: str, arguments: dict) -> Any:
        return await self.request("operation.call", {
            "session": self._session(session), "operation": operation,
            "arguments": arguments,
        })

    async def prepare_files(self, session: str, *, target: str, request_id: str,
                            text: str, entries: Sequence[Mapping], previous_manifest=None,
                            attachment_fallback=None) -> dict:
        """Prepare caller-read bytes only. No body send, ACK, retry or source-path read."""
        limit = self.initialization.get('limits', {}).get('fileUploadChunkBytes')
        if type(limit) is not int or not 0 < limit <= 192 * 1024:
            raise ValueError('server does not advertise supported chunk preparation')
        if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= 16:
            raise ValueError('1 to 16 caller-read entries required')
        frozen, specs, total = [], [], 0
        for entry in entries:
            if not isinstance(entry, Mapping) or set(entry) - {'name', 'data', 'source_version'}:
                raise ValueError('entries accept name, data and optional source_version only')
            data = entry.get('data')
            if not isinstance(data, (bytes, bytearray, memoryview)):
                raise ValueError('entry data must be caller-read bytes')
            size = data.nbytes if isinstance(data, memoryview) else len(data)
            total += size
            if size > 1048576 or total > 4194304:
                raise ValueError('entry or bundle exceeds 1MiB/4MiB limit')
            data = bytes(data)
            spec = {'name': entry.get('name'), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            if 'source_version' in entry:
                spec['source_version'] = entry['source_version']
            specs.append(spec)
            frozen.append(data)
        params = {'session': self._session(session), 'target': target, 'request_id': request_id,
                  'text': text, 'entries': specs}
        if previous_manifest is not None:
            params['previous_manifest'] = previous_manifest
        if attachment_fallback is not None:
            params['attachment_fallback'] = attachment_fallback
        opened = await self.request('files.upload.open', params)
        if not isinstance(opened, dict):
            raise TransportError('invalid upload open response')
        if opened.get('state') == 'frozen':
            return dict(opened, body_sent=False)
        chunk = opened.get('chunk_bytes')
        offsets = opened.get('offsets')
        if (opened.get('state') != 'uploading' or type(chunk) is not int or not 0 < chunk <= limit or not isinstance(offsets, list)
                or len(offsets) != len(frozen) or any(type(offset) is not int or not 0 <= offset <= len(data)
                                                    for offset, data in zip(offsets, frozen))):
            raise TransportError('invalid upload progress response')
        for index, (data, offset) in enumerate(zip(frozen, offsets)):
            for start in range(offset, len(data), chunk):
                await self.request('files.upload.write', {'session': session, 'upload': opened['upload'],
                    'entry': index, 'offset': start, 'base64': base64.b64encode(data[start:start + chunk]).decode('ascii')})
        return await self.request('files.upload.commit', {'session': session, 'upload': opened['upload']})

    async def events_subscribe(self, session: str) -> Any:
        return await self.request("events.subscribe", {"session": self._session(session)})

    async def delivery_report(self, session: str, ident: str, state: str, token=None) -> Any:
        params = {"session": self._session(session), "id": ident, "state": state}
        if token is not None:
            params["token"] = token
        return await self.request("delivery.report", params)

    async def next_notification(self) -> dict:
        """Return the next method/params envelope; raise on transport closure."""
        item = await self._notifications.get()
        if isinstance(item, TransportError):
            self._notifications.put_nowait(item)
            raise item
        return item

    async def _read_stdout(self):
        buffered = b""
        try:
            while True:
                chunk = await self.process.stdout.read(65536)
                if not chunk:
                    if buffered:
                        raise TransportError("unterminated JSONL frame at EOF")
                    raise TransportError("peer closed stdout (EOF)")
                buffered += chunk
                while b"\n" in buffered:
                    line, buffered = buffered.split(b"\n", 1)
                    message = json.loads(line.decode("utf-8"),
                                         object_pairs_hook=_strict_object,
                                         parse_constant=_invalid_constant)
                    self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fail(exc if isinstance(exc, TransportError) else
                       TransportError(f"invalid RPC stream: {exc}"))
            # Keep draining after malformed data so even a noisy peer can be reaped.
            while await self.process.stdout.read(65536):
                pass

    def _dispatch(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise TransportError("expected a JSON-RPC 2.0 object")
        if "method" in message:
            if ("id" in message or not isinstance(message["method"], str)
                    or not isinstance(message.get("params", {}), dict)
                    or "result" in message or "error" in message):
                raise TransportError("expected a notification, not a peer request")
            self._notifications.put_nowait(message)
            return
        if (not isinstance(message.get("id"), str)
                or ("result" in message) == ("error" in message)):
            raise TransportError("invalid RPC response")
        error = message.get("error")
        if "error" in message and (not isinstance(error, dict)
                or type(error.get("code")) is not int
                or not isinstance(error.get("message"), str)):
            raise TransportError("invalid RPC error object")
        future = self._pending.pop(message["id"], None)
        if future is None or future.done():
            return  # A response to a cancelled request is harmless.
        if "error" in message:
            future.set_exception(RpcError(error["code"], error["message"], error.get("data")))
        else:
            future.set_result(message["result"])

    async def _read_stderr(self):
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            while True:
                chunk = await self.process.stderr.read(4096)
                text = decoder.decode(chunk, final=not chunk)
                if text:
                    self._on_stderr(text)
                if not chunk:
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fail(TransportError(f"stderr consumer failed: {exc}"))
            while await self.process.stderr.read(65536):
                pass

    def _fail(self, error):
        if self._failure is not None:
            return
        self._failure = error
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()
        self._notifications.put_nowait(error)
        self._close_task = asyncio.create_task(self._shutdown())

    async def _shutdown(self):
        self.process.stdin.close()
        try:
            for signal in (None, "terminate", "kill"):
                if self.process.returncode is not None:
                    break
                if signal:
                    try:
                        getattr(self.process, signal)()
                    except ProcessLookupError:
                        pass
                try:
                    await asyncio.wait_for(self.process.wait(), self._close_timeout)
                    break
                except asyncio.TimeoutError:
                    if signal == "kill":
                        await self.process.wait()
        finally:
            for task in (self._reader, self._stderr_reader):
                task.cancel()
            await asyncio.gather(self._reader, self._stderr_reader, return_exceptions=True)

    async def close(self):
        """Reject pending calls, close stdin, then terminate/kill and reap the peer."""
        self._fail(TransportError("client closed"))
        await asyncio.shield(self._close_task)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()


class XsmHostClient(XsmClient):
    """Trusted host UI bridge. Do not expose this object to model tool calls."""

    async def respond_to_decision(self, event, *, displayed, source_id, answer=None, action="accept"):
        if not isinstance(event, dict) or event.get("method") != "decision/request":
            raise ValueError("an actual host decision/request event is required")
        params = event.get("params") or {}
        return await self._request("decision.response", {
            "session": params.get("session"), "questionId": params.get("questionId"),
            "challenge": params.get("challenge"), "displayed": displayed,
            "source_id": source_id, "action": action, "answer": answer})

    async def abandon_decision(self, event):
        if not isinstance(event, dict) or event.get("method") != "decision/request":
            raise ValueError("an actual host decision/request event is required")
        params = event.get("params") or {}
        return await self._request("decision.abandon", {
            "session": params.get("session"), "questionId": params.get("questionId"),
            "challenge": params.get("challenge")})
