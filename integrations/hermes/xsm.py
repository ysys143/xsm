"""Hermes 0.22.5 plugin entry. Experimental pull tools; native push/UI are not yet wired."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
import sys
import threading


def _sdk(root):
    directory = root / "clients/python"
    name = "_xsm_sdk_" + hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:24]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, directory / "__init__.py",
                                                     submodule_search_locations=[str(directory)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        try:
            spec.loader.exec_module(package)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return __import__(name + ".xsm_host", fromlist=["XsmHost"])


def _component_lease(root, python, env=None):
    root = root.resolve()
    if root.parent.name != "runtime" or not re.fullmatch(r"[0-9a-f]{12}", root.name):
        return lambda: None
    environment = dict(os.environ if env is None else env, XSM_HOME=str(root.parent.parent))
    code = ("import json,sys;sys.path.insert(0,sys.argv[1]);"
            "from xsm.component_leases import hold,release;"
            "record=json.load(sys.stdin);"
            "print(json.dumps(hold('hermes-plugin',int(sys.argv[2])) if record is None "
            "else release(record,int(sys.argv[2]))))")
    def request(record):
        result = subprocess.run([python, "-B", "-c", code, str(root), str(os.getpid())],
            input=json.dumps(record), capture_output=True, text=True, env=environment, timeout=10)
        if result.returncode:
            raise RuntimeError("Hermes component lease failed: " + result.stderr[-2000:])
        return json.loads(result.stdout)
    record = request(None)
    if (record.get("root") != str(root) or record.get("pid") != os.getpid() or
            record.get("component") != "hermes-plugin"):
        raise RuntimeError("Hermes component lease identity differs")
    return lambda: request(record)


class HermesBinding:
    def __init__(self, context, *, command=None, env=None):
        from hermes_constants import get_hermes_home
        self.context = context
        self.root = Path(__file__).resolve().parents[2]
        self.profile = str(get_hermes_home().resolve())
        self.sdk = _sdk(self.root)
        self.command = command or [sys.executable, "-B", "-c",
            "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
            str(self.root), "protocol", "serve", "--stdio"]
        self.env = env
        self.hosts = {}
        self.host_locks = {}
        self.closed = False
        self.closing = False
        self.finalizing = set()
        self.monitors = {}
        self.states = {}
        self.release_component = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="xsm-hermes", daemon=True)
        self.thread.start()

    def _run(self, coroutine):
        if self.closed:
            coroutine.close()
            raise RuntimeError("xsm Hermes binding closed")
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def _identity(self, session_id):
        sid = str(session_id or "")
        if not sid:
            raise RuntimeError("native dispatcher session identity is missing")
        cwd = self.context.session_cwd()
        if not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
            raise RuntimeError("native caller has no existing absolute workspace")
        return sid, str(Path(cwd).resolve())

    def _host_lock(self, sid):
        return self.host_locks.setdefault(sid, asyncio.Lock())

    async def _host(self, sid, cwd, *, rebind=False):
        async with self._host_lock(sid):
            if self.closed or self.closing or sid in self.finalizing:
                raise RuntimeError("native participation is closing")
            if sid in self.hosts and self.hosts[sid][0] != cwd:
                if not rebind:
                    raise RuntimeError("native workspace changed; wait for the native session-start hook")
                monitor = self.monitors.pop(sid, None)
                if monitor and monitor is not asyncio.current_task():
                    monitor.cancel()
                    await asyncio.gather(monitor, return_exceptions=True)
                _, previous = self.hosts.pop(sid)
                await (await previous).close()
            if sid in self.hosts:
                _, previous = self.hosts[sid]
                existing = await previous
                if getattr(existing, "failure", None) is not None or getattr(existing, "closed", False):
                    # Replace participation without replaying a failed operation.
                    await existing.close()
                    self.hosts.pop(sid)
            return await self._open_host(sid, cwd)

    async def _open_host(self, sid, cwd):
        if self.closed or self.closing or sid in self.finalizing:
            raise RuntimeError("native participation is closing")
        if sid not in self.hosts:
            pending = asyncio.create_task(self.sdk.XsmHost.open(runtime="hermes", profile=self.profile,
                conversation=sid, cwd=cwd, command=self.command, env=self.env))
            self.hosts[sid] = (cwd, pending)
            try:
                await pending
            except BaseException:
                if self.hosts.get(sid, (None, None))[1] is pending:
                    self.hosts.pop(sid, None)
                raise
        _, pending = self.hosts[sid]
        host = await pending
        if self.closed or self.closing or sid in self.finalizing:
            if self.hosts.get(sid, (None, None))[1] is pending:
                self.hosts.pop(sid, None)
            await host.close()
            raise RuntimeError("native participation is closing")
        if not self.closing and sid not in self.finalizing and sid not in self.monitors:
            self.monitors[sid] = asyncio.create_task(self._monitor(sid, cwd))
        return host

    async def _monitor(self, sid, cwd):
        delay = .25
        try:
            while not self.closed and not self.closing and sid not in self.finalizing:
                await asyncio.sleep(delay)
                try:
                    pair = self.hosts.get(sid)
                    if pair:
                        if pair[0] != cwd:
                            return
                        if not pair[1].done():
                            continue
                        host = pair[1].result()
                        failure = getattr(host, "failure", None)
                        if failure is None:
                            delay = .25
                            continue
                        if not isinstance(failure, getattr(self.sdk, "TransportError", ())):
                            return
                    host = await self._host(sid, cwd)
                    await host.update(self.states.get(sid, "idle"))
                    delay = .25
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    print("xsm:", str(error), file=sys.stderr)
                    if not isinstance(error, getattr(self.sdk, "TransportError", ())):
                        return
                    delay = min(delay * 2, 5)
        finally:
            if self.monitors.get(sid) is asyncio.current_task():
                self.monitors.pop(sid, None)

    async def _call(self, sid, cwd, operation, args):
        return await (await self._host(sid, cwd)).call(operation, args)

    def handler(self, operation):
        def call(args, *, session_id="", **_native):
            sid, cwd = self._identity(session_id)
            return json.dumps(self._run(self._call(sid, cwd, operation, args)), ensure_ascii=False)
        return call

    def start(self, session_id="", **_native):
        sid, cwd = self._identity(session_id)
        async def update():
            self.states[sid] = "busy"
            await (await self._host(sid, cwd, rebind=True)).update("busy")
        self._run(update())

    def settled(self, session_id="", **_native):
        async def update():
            if session_id in self.hosts or session_id in self.monitors:
                self.states[session_id] = "idle"
            if session_id in self.hosts:
                await (await self.hosts[session_id][1]).update("idle")
        self._run(update())

    def finalize(self, session_id="", **_native):
        async def close():
            self.finalizing.add(session_id)
            try:
                monitor = self.monitors.pop(session_id, None)
                if monitor:
                    monitor.cancel()
                    await asyncio.gather(monitor, return_exceptions=True)
                async with self._host_lock(session_id):
                    pair = self.hosts.pop(session_id, None)
                    self.states.pop(session_id, None)
                    if pair:
                        await (await pair[1]).close()
            finally:
                self.finalizing.discard(session_id)
        self._run(close())

    def reset(self, old_session_id="", new_session_id="", **_native):
        if old_session_id and old_session_id != new_session_id:
            self.finalize(session_id=old_session_id)

    def _release_component(self):
        if self.release_component is not None:
            self.release_component()
            self.release_component = None

    def close(self):
        if self.closed:
            self._release_component()
            return
        async def shutdown():
            self.closing = True
            monitors = list(self.monitors.values())
            self.monitors.clear()
            for monitor in monitors:
                monitor.cancel()
            await asyncio.gather(*monitors, return_exceptions=True)
            for _, pending in list(self.hosts.values()):
                if not pending.done():
                    pending.cancel()
            for lock in list(self.host_locks.values()):
                async with lock:
                    pass
            pairs = list(self.hosts.values())
            self.hosts.clear()
            self.states.clear()
            hosts = await asyncio.gather(*(pair[1] for pair in pairs), return_exceptions=True)
            await asyncio.gather(*(host.close() for host in hosts if not isinstance(host, BaseException)))
        self._run(shutdown())
        self.closed = True
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("xsm Hermes coordinator thread did not stop")
        self.loop.close()
        self._release_component()


def register(context, *, command=None, env=None):
    """Register with an optional installer-pinned backend and isolated environment."""
    binding = HermesBinding(context, command=command, env=env)
    try:
        binding.release_component = _component_lease(binding.root, binding.command[0], binding.env)
        context.on_unload(binding.close)
        client_type = binding.sdk.XsmHost.__module__.replace("xsm_host", "xsm_client")
        client_type = __import__(client_type, fromlist=["XsmClient"]).XsmClient
        async def describe():
            async with await client_type.connect(binding.command, cwd=str(binding.root), env=binding.env) as client:
                return (await client.request("operations/list"))["operations"]
        for operation in binding._run(describe()):
            context.register_tool(name=operation["name"], toolset="xsm",
                schema={"name": operation["name"], "description": operation["description"],
                        "parameters": operation["inputSchema"]}, handler=binding.handler(operation["name"]),
                description=operation["description"])
        for name, callback in (("on_session_start", binding.start), ("on_session_end", binding.settled),
                ("on_session_finalize", binding.finalize), ("on_session_delete", binding.finalize),
                ("on_session_reset", binding.reset)):
            context.register_hook(name, callback)
    except BaseException:
        binding.close()
        raise
    return binding
