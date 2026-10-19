"""LocalToolBackend: real Level 1-3 tools (filesystem, processes, headless browser).

WHAT THIS IS: a *workspace-confined tool runner*. It never sends mouse/keyboard input,
never captures or controls the user's desktop, and has no GUI capability.

WHAT THIS IS NOT: OS-level isolation. Filesystem tools are confined to allowed roots
(path checks incl. symlink resolution), but a subprocess runs with the user's own
privileges. Process execution is therefore gated by the action policy; real
containment of untrusted code needs a Windows Sandbox / VM backend.

GUI applications launched through process tools WOULD appear on the user's desktop;
the default policy blocks well-known GUI launchers, but that is best-effort.
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence

from ..actions import (Action, ActionErrorCode, ActionFailure, ActionKind, ActionResult,
                       BROWSER_KINDS, FS_KINDS, PROCESS_KINDS)
from ..backend import BackendStatus, ExecutionBackend, ExecutionEnvironment
from ..cancellation import CancelToken
from .browser import BrowserController, BrowserEngine, PlaywrightEngine

log = logging.getLogger("background_agent")

SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_LIST_ENTRIES = 500


def _is_within(path: Path, root: Path) -> bool:
    try:
        a, b = os.path.normcase(str(path)), os.path.normcase(str(root))
        return os.path.commonpath([a, b]) == b
    except ValueError:
        return False


def sanitized_environment() -> Dict[str, str]:
    """Child processes never inherit API keys/tokens (e.g. GEMINI_API_KEY)."""
    return {k: v for k, v in os.environ.items() if not any(m in k.upper() for m in SECRET_ENV_MARKERS)}


def kill_process_tree(proc: "subprocess.Popen[bytes]") -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


class LocalToolEnvironment(ExecutionEnvironment):
    def __init__(self, workspace: Path, roots: Sequence[Path], capabilities: FrozenSet[ActionKind],
                 browser: Optional[BrowserController], *, max_read_bytes: int, max_output_chars: int,
                 cleanup_timeout: float) -> None:
        self.workspace = workspace
        self.capabilities = capabilities
        self._roots = list(roots)
        self._browser = browser
        self._max_read = max_read_bytes
        self._max_out = max_output_chars
        self._cleanup_timeout = cleanup_timeout
        self._abort = threading.Event()
        self._procs: List["subprocess.Popen[bytes]"] = []
        self._plock = threading.Lock()
        self._closed = False
        self._fs: Dict[ActionKind, Callable[[Dict], ActionResult]] = {
            ActionKind.FS_STAT: self._stat, ActionKind.FS_READ: self._read, ActionKind.FS_WRITE: self._write,
            ActionKind.FS_LIST: self._list, ActionKind.FS_MKDIR: self._mkdir, ActionKind.FS_MOVE: self._move,
            ActionKind.FS_COPY: self._copy, ActionKind.FS_DELETE: self._delete,
        }

    def resolve_path(self, raw: object) -> Path:
        if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "a non-empty path string is required")
        p = Path(raw)
        if not p.is_absolute():
            p = self.workspace / p
        resolved = p.resolve(strict=False)
        if os.name == "nt":
            if any(":" in part for part in resolved.parts[1:]):
                raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "alternate data streams are not allowed")
            if any(part.split(".")[0].upper() in WINDOWS_RESERVED for part in resolved.parts[1:]):
                raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "reserved device name")
        if not any(_is_within(resolved, root) for root in self._roots):
            raise ActionFailure(ActionErrorCode.OUTSIDE_WORKSPACE, "path is outside the allowed folders")
        return resolved

    def _is_root(self, path: Path) -> bool:
        return any(os.path.normcase(str(path)) == os.path.normcase(str(r)) for r in self._roots)

    def execute(self, action: Action, *, deadline: float, cancel: CancelToken) -> ActionResult:
        if self._abort.is_set():
            return ActionResult.failure(ActionErrorCode.CANCELLED, "environment was aborted")
        try:
            if action.kind in FS_KINDS:
                return self._fs[action.kind](dict(action.params))
            if action.kind in (ActionKind.PROCESS_RUN, ActionKind.PROCESS_SHELL):
                return self._process(action, deadline, cancel)
            if action.kind in BROWSER_KINDS and self._browser is not None:
                return self._browser.execute(action, deadline, cancel)
        except ActionFailure as f:
            return ActionResult.failure(f.code, f.message)
        except PermissionError as e:
            return ActionResult.failure(ActionErrorCode.PERMISSION_DENIED, str(e))
        except FileNotFoundError as e:
            return ActionResult.failure(ActionErrorCode.NOT_FOUND, str(e))
        except OSError as e:
            return ActionResult.failure(ActionErrorCode.IO_ERROR, f"{type(e).__name__}: {e}")
        return ActionResult.failure(ActionErrorCode.UNSUPPORTED, f"{action.kind.value} is not supported")

    def _stat(self, p: Dict) -> ActionResult:
        path = self.resolve_path(p.get("path"))
        exists = path.exists()
        size = path.stat().st_size if exists and path.is_file() else 0
        return ActionResult.success("exists" if exists else "does not exist",
                                    data={"path": str(path), "exists": exists, "is_file": path.is_file(),
                                          "is_dir": path.is_dir(), "size": size})

    def _read(self, p: Dict) -> ActionResult:
        path = self.resolve_path(p.get("path"))
        if not path.is_file():
            raise ActionFailure(ActionErrorCode.NOT_FOUND, "file does not exist")
        limit = min(int(p.get("max_bytes") or self._max_read), self._max_read)
        with open(path, "rb") as fh:
            data = fh.read(limit + 1)
        text = data[:limit].decode(p.get("encoding", "utf-8"), errors="replace")
        return ActionResult.success(text + ("\n[truncated]" if len(data) > limit else ""),
                                    data={"truncated": len(data) > limit})

    def _write(self, p: Dict) -> ActionResult:
        path = self.resolve_path(p.get("path"))
        content = p.get("content", "")
        if not isinstance(content, str):
            raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "content must be a string")
        if path.exists() and not p.get("overwrite"):
            raise ActionFailure(ActionErrorCode.ALREADY_EXISTS, "file exists; pass overwrite=true to replace it")
        if path.is_dir():
            raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "path is a directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".bg-write-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(content.encode(p.get("encoding", "utf-8")))
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return ActionResult.success(f"wrote {path.stat().st_size} bytes", produced_paths=(str(path),))

    def _list(self, p: Dict) -> ActionResult:
        path = self.resolve_path(p.get("path") or ".")
        if not path.is_dir():
            raise ActionFailure(ActionErrorCode.NOT_FOUND, "folder does not exist")
        lines = []
        for i, child in enumerate(sorted(path.iterdir(), key=lambda c: c.name.lower())):
            if i >= MAX_LIST_ENTRIES:
                lines.append(f"... more than {MAX_LIST_ENTRIES} entries")
                break
            lines.append(f"d {child.name}" if child.is_dir() else f"f {child.name} {child.stat().st_size}")
        return ActionResult.success("\n".join(lines))

    def _mkdir(self, p: Dict) -> ActionResult:
        path = self.resolve_path(p.get("path"))
        path.mkdir(parents=True, exist_ok=True)
        return ActionResult.success("created")

    def _src_dst(self, p: Dict):
        src, dst = self.resolve_path(p.get("src")), self.resolve_path(p.get("dst"))
        if not src.exists():
            raise ActionFailure(ActionErrorCode.NOT_FOUND, "source does not exist")
        if self._is_root(src):
            raise ActionFailure(ActionErrorCode.PERMISSION_DENIED, "cannot move/copy an allowed root itself")
        if dst.exists() and not p.get("overwrite"):
            raise ActionFailure(ActionErrorCode.ALREADY_EXISTS, "destination exists; pass overwrite=true")
        dst.parent.mkdir(parents=True, exist_ok=True)
        return src, dst

    def _move(self, p: Dict) -> ActionResult:
        src, dst = self._src_dst(p)
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        shutil.move(str(src), str(dst))
        return ActionResult.success("moved", produced_paths=(str(dst),))

    def _copy(self, p: Dict) -> ActionResult:
        src, dst = self._src_dst(p)
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
        return ActionResult.success("copied", produced_paths=(str(dst),))

    def _delete(self, p: Dict) -> ActionResult:
        path = self.resolve_path(p.get("path"))
        if self._is_root(path):
            raise ActionFailure(ActionErrorCode.PERMISSION_DENIED, "cannot delete an allowed root itself")
        if not path.exists():
            raise ActionFailure(ActionErrorCode.NOT_FOUND, "path does not exist")
        if path.is_dir():
            if not p.get("recursive"):
                raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "folder delete needs recursive=true")
            shutil.rmtree(path)
        else:
            path.unlink()
        return ActionResult.success("deleted")

    def _process(self, action: Action, deadline: float, cancel: CancelToken) -> ActionResult:
        p, shell = action.params, action.kind is ActionKind.PROCESS_SHELL
        if shell:
            cmd = p.get("command")
            if not isinstance(cmd, str) or not cmd.strip():
                raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "'command' is required")
        else:
            cmd = p.get("argv")
            if not isinstance(cmd, (list, tuple)) or not cmd or not all(isinstance(a, str) for a in cmd):
                raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "'argv' must be a non-empty list of strings")
        cwd = self.resolve_path(p["cwd"]) if p.get("cwd") else self.workspace
        limit = deadline
        if p.get("timeout_seconds"):
            limit = min(limit, time.monotonic() + float(p["timeout_seconds"]))

        kwargs: Dict = dict(stdin=subprocess.DEVNULL, cwd=str(cwd), env=sanitized_environment(), shell=shell)
        if os.name == "nt":
            kwargs["creationflags"] = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                       | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        else:
            kwargs["start_new_session"] = True
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                proc = subprocess.Popen(cmd, stdout=out, stderr=err, **kwargs)
            except FileNotFoundError:
                return ActionResult.failure(ActionErrorCode.NOT_FOUND, "executable not found")
            except OSError as e:
                return ActionResult.failure(ActionErrorCode.IO_ERROR, f"could not start process: {e}")
            with self._plock:
                self._procs.append(proc)
            try:
                while proc.poll() is None:
                    if self._abort.is_set() or cancel.is_cancelled:
                        kill_process_tree(proc)
                        return ActionResult.failure(ActionErrorCode.CANCELLED, "process killed: task cancelled")
                    if time.monotonic() >= limit:
                        kill_process_tree(proc)
                        return ActionResult.failure(ActionErrorCode.TIMEOUT, "process killed: time limit reached")
                    cancel.wait(0.05)
                if self._abort.is_set() or cancel.is_cancelled:
                    return ActionResult.failure(ActionErrorCode.CANCELLED, "process killed: task cancelled")
                text = self._tail(out) + (("\n[stderr]\n" + self._tail(err)) if err.tell() else "")
            finally:
                with self._plock:
                    if proc in self._procs:
                        self._procs.remove(proc)
                kill_process_tree(proc)
        if proc.returncode == 0:
            return ActionResult.success(text, data={"returncode": 0})
        return ActionResult.failure(ActionErrorCode.NONZERO_EXIT, f"exit code {proc.returncode}",
                                    output=text, data={"returncode": proc.returncode})

    def _tail(self, fh) -> str:
        size = fh.seek(0, os.SEEK_END)
        fh.seek(max(0, size - self._max_out))
        text = fh.read().decode("utf-8", errors="replace")
        return ("[earlier output truncated]\n" if size > self._max_out else "") + text

    def abort(self) -> None:
        self._abort.set()
        with self._plock:
            procs = list(self._procs)
        for proc in procs:
            kill_process_tree(proc)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.abort()
        if self._browser is not None:
            self._browser.close(self._cleanup_timeout)


class LocalToolBackend(ExecutionBackend):
    name = "local-tools"
    max_concurrency = 1

    def __init__(self, workspace_root: Path, *, extra_allowed_roots: Sequence[Path] = (),
                 enable_browser: bool = False,
                 browser_engine_factory: Optional[Callable[[], BrowserEngine]] = None,
                 allowed_kinds: Optional[Iterable[ActionKind]] = None,
                 max_read_bytes: int = 1_000_000, max_output_chars: int = 20_000,
                 cleanup_timeout: float = 15.0) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.extra_roots = [Path(r).resolve() for r in extra_allowed_roots]
        self.enable_browser = enable_browser
        self.allowed_kinds = frozenset(allowed_kinds) if allowed_kinds is not None else None
        self._engine_factory = browser_engine_factory or PlaywrightEngine
        self._max_read, self._max_out, self._cleanup = max_read_bytes, max_output_chars, cleanup_timeout

    def check_available(self) -> BackendStatus:
        try:
            self.workspace_root.mkdir(parents=True, exist_ok=True)
            probe = tempfile.NamedTemporaryFile(dir=self.workspace_root, prefix=".probe-", delete=True)
            probe.close()
        except OSError as e:
            return BackendStatus(False, f"workspace is not writable: {e}")
        return BackendStatus(True)

    def open_environment(self, task_id: str) -> LocalToolEnvironment:
        workspace = (self.workspace_root / task_id).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        caps = set(FS_KINDS) | set(PROCESS_KINDS)
        controller = None
        if self.enable_browser:
            caps |= set(BROWSER_KINDS)
            controller = BrowserController(self._engine_factory, lambda raw: self._resolve_for(workspace, raw))
        if self.allowed_kinds is not None:
            caps &= self.allowed_kinds
        env = LocalToolEnvironment(workspace, [workspace, *self.extra_roots], frozenset(caps), controller,
                                   max_read_bytes=self._max_read, max_output_chars=self._max_out,
                                   cleanup_timeout=self._cleanup)
        if controller is not None:
            controller._resolve = env.resolve_path
        return env

    @staticmethod
    def _resolve_for(workspace: Path, raw: str) -> Path:
        return workspace / raw
