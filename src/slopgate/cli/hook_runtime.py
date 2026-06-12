"""Hook runtime CLI commands."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from slopgate.cli._claude_retry import claude_team_event_feedback
from slopgate.cli.io import (
    CliInputError,
    dump_output,
    load_stdin_json,
    report_cli_input_error,
    string_arg,
)
from slopgate.constants import PLATFORM_CLAUDE, UNKNOWN_VALUE
from slopgate.daemon.paths import default_daemon_socket_path
from slopgate.util import logger

SLOPGATE_DAEMON_SOCKET_ENV = "SLOPGATE_DAEMON_SOCKET"
HOOK_HANDLE_EVENT = "handle"
CLAUDE_TEAM_EVENT_EXIT_CODE = 2


def cmd_daemon(args: argparse.Namespace) -> int:
    socket_path = _daemon_socket_path_arg(args)
    max_requests = _positive_int_arg(args, "max_requests")
    workers = _positive_int_arg(args, "workers")
    serial = getattr(args, "serial", False) is True

    from slopgate.daemon.hook import evaluate_hook_request
    from slopgate.daemon.scheduler import DaemonServerOptions
    from slopgate.daemon.server import HookDaemonServer

    logger.info(
        "hook daemon cli start",
        socket_path=str(socket_path),
        max_requests=max_requests or 0,
        workers=workers or 0,
        serial=serial,
    )
    HookDaemonServer(
        socket_path,
        evaluate_hook_request,
        options=DaemonServerOptions(workers=workers, serial=serial),
    ).serve(max_requests=max_requests)
    return 0


def cmd_handle(args: argparse.Namespace) -> int:
    try:
        payload = load_stdin_json()
    except CliInputError as exc:
        return report_cli_input_error(exc)
    if not payload:
        return 0
    platform = string_arg(args, "platform", PLATFORM_CLAUDE)
    logger.info(
        "hook cli handle payload",
        platform=platform,
        payload_present=True,
        target="daemon_or_engine",
    )
    daemon_exit_code = _try_handle_via_daemon(payload, platform)
    if daemon_exit_code is not None:
        return daemon_exit_code

    from slopgate.engine import evaluate_payload

    result = evaluate_payload(payload, platform=platform)
    if platform.strip().lower() == PLATFORM_CLAUDE:
        feedback = claude_team_event_feedback(result)
        if feedback:
            _ = sys.stderr.write(feedback.rstrip() + "\n")
            return CLAUDE_TEAM_EVENT_EXIT_CODE
    return dump_output(result.output)


def _try_handle_via_daemon(payload: dict[str, object], platform: str) -> int | None:
    socket_path = _daemon_socket_path_for_handle()
    if socket_path is None:
        return None

    from slopgate.daemon import (
        DAEMON_ACCEPTED_FAILURE_ERROR,
        DaemonRequest,
        send_daemon_request,
    )

    logger.info(
        "hook cli daemon handoff", platform=platform, socket_path=str(socket_path)
    )
    response = send_daemon_request(
        socket_path,
        DaemonRequest(payload=payload, platform=platform, event=HOOK_HANDLE_EVENT),
    )
    if not response.ok:
        if response.error == DAEMON_ACCEPTED_FAILURE_ERROR:
            if response.stderr:
                _ = sys.stderr.write(response.stderr)
            return response.exit_code or 1
        logger.warning(
            "hook cli daemon fallback",
            platform=platform,
            socket_path=str(socket_path),
            error=response.error or UNKNOWN_VALUE,
        )
        return None
    if response.stderr:
        _ = sys.stderr.write(response.stderr)
    if response.output:
        _ = dump_output(response.output)
    return response.exit_code


def _daemon_socket_path_arg(args: argparse.Namespace) -> Path:
    socket_path = string_arg(args, "socket")
    return Path(socket_path) if socket_path else default_daemon_socket_path()


def _daemon_socket_path_for_handle() -> Path | None:
    socket_path = os.environ.get(SLOPGATE_DAEMON_SOCKET_ENV)
    if socket_path:
        logger.info(
            "hook cli daemon socket selected",
            source="env",
            socket_path=socket_path,
        )
        return Path(socket_path)
    default_path = default_daemon_socket_path()
    return default_path if default_path.exists() else None


def _positive_int_arg(args: argparse.Namespace, name: str) -> int | None:
    value = getattr(args, name, None)
    return value if isinstance(value, int) and value > 0 else None


def cmd_handle_async(_args: argparse.Namespace) -> int:
    from slopgate.async_jobs import run_async_jobs

    try:
        payload = load_stdin_json()
    except CliInputError as exc:
        return report_cli_input_error(exc)
    logger.info("hook cli async jobs", payload_present=bool(payload))
    summary, _errors = run_async_jobs(payload)
    if summary:
        _ = sys.stdout.write(summary + "\n")
    return 0
