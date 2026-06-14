"""Project-aware daemon request scheduling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import threading
import time

from slopgate.config import resolve_repo_root
from slopgate.constants import UNKNOWN_VALUE
from slopgate.daemon.protocol import DaemonRequest, DaemonResponse
from slopgate.lint._config import reset_config, set_quality_scope
from slopgate.quality.constant_index import reset_session_constant_index
from slopgate.util import logger

HookRequestHandler = Callable[[DaemonRequest], DaemonResponse]
DEFAULT_WORKERS = 4
UNKNOWN_REPO_KEY = UNKNOWN_VALUE


@dataclass(frozen=True, slots=True)
class DaemonServerOptions:
    workers: int | None = None
    serial: bool = False

    @property
    def worker_count(self) -> int:
        return max(1, self.workers or DEFAULT_WORKERS)


class RepoLockRegistry:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def lock_for(self, repo_key: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(repo_key)
            if lock is None:
                lock = threading.Lock()
                self._locks[repo_key] = lock
            return lock


@dataclass(frozen=True, slots=True)
class EvaluationLogContext:
    socket_path: Path
    request: DaemonRequest
    repo_key: str
    request_id: str


class DaemonRequestScheduler:
    def __init__(self, socket_path: Path, handler: HookRequestHandler) -> None:
        self._socket_path = socket_path
        self._handler = handler
        self._repo_locks = RepoLockRegistry()

    def evaluate(self, request: DaemonRequest) -> DaemonResponse:
        repo_key = repo_key_for_request(request)
        request_id = _payload_string(request, "request_id", "session_id")
        log_context = EvaluationLogContext(
            socket_path=self._socket_path,
            request=request,
            repo_key=repo_key,
            request_id=request_id or UNKNOWN_VALUE,
        )
        lock = self._repo_locks.lock_for(repo_key)
        wait_start = time.monotonic()
        with lock:
            wait_ms = int((time.monotonic() - wait_start) * 1000)
            eval_start = time.monotonic()
            _log_evaluate_start(log_context, wait_ms)
            _reset_daemon_request_context()
            try:
                response = self._handler(request)
                duration_ms = int((time.monotonic() - eval_start) * 1000)
                _log_evaluate_done(log_context, response, duration_ms)
                return response
            finally:
                _reset_daemon_request_context()


def repo_key_for_request(request: DaemonRequest) -> str:
    cwd = _payload_string(request, "cwd", "directory")
    if cwd is None:
        return UNKNOWN_REPO_KEY
    try:
        path = Path(cwd).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return UNKNOWN_REPO_KEY
    repo_root = resolve_repo_root(path)
    if repo_root is not None:
        return str(repo_root)
    fallback = path if path.is_dir() else path.parent
    return str(fallback)


def _payload_string(
    request: DaemonRequest, primary_key: str, fallback_key: str
) -> str | None:
    raw_value = request.payload.get(primary_key) or request.payload.get(fallback_key)
    return raw_value if isinstance(raw_value, str) and raw_value else None


def _reset_daemon_request_context() -> None:
    reset_config()
    _ = set_quality_scope(None)
    reset_session_constant_index()


def _log_evaluate_start(log_context: EvaluationLogContext, wait_ms: int) -> None:
    logger.info(
        "hook daemon evaluate start",
        socket_path=str(log_context.socket_path),
        platform=log_context.request.platform or UNKNOWN_VALUE,
        event_name=log_context.request.event or UNKNOWN_VALUE,
        repo_key=log_context.repo_key,
        request_id=log_context.request_id,
        wait_ms=wait_ms,
    )


def _log_evaluate_done(
    log_context: EvaluationLogContext,
    response: DaemonResponse,
    duration_ms: int,
) -> None:
    logger.info(
        "hook daemon evaluate done",
        socket_path=str(log_context.socket_path),
        platform=log_context.request.platform or UNKNOWN_VALUE,
        event_name=log_context.request.event or UNKNOWN_VALUE,
        repo_key=log_context.repo_key,
        request_id=log_context.request_id,
        duration_ms=duration_ms,
        status="ok" if response.ok else "error",
    )
