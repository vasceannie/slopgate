"""Resident hook daemon transport."""

from slopgate.daemon.client import DAEMON_ACCEPTED_FAILURE_ERROR, send_daemon_request
from slopgate.daemon.hook import CLAUDE_TEAM_EVENT_EXIT_CODE, evaluate_hook_request
from slopgate.daemon.protocol import DaemonRequest, DaemonResponse
from slopgate.daemon.server import HookDaemonServer

__all__ = [
    "CLAUDE_TEAM_EVENT_EXIT_CODE",
    "DAEMON_ACCEPTED_FAILURE_ERROR",
    "DaemonRequest",
    "DaemonResponse",
    "HookDaemonServer",
    "evaluate_hook_request",
    "send_daemon_request",
]
