"""Resident hook daemon transport."""

from slopgate.daemon.client import send_daemon_request
from slopgate.daemon.hook import CLAUDE_TEAM_EVENT_EXIT_CODE, evaluate_hook_request
from slopgate.daemon.protocol import DaemonRequest, DaemonResponse
from slopgate.daemon.server import HookDaemonServer

__all__ = [
    "CLAUDE_TEAM_EVENT_EXIT_CODE",
    "DaemonRequest",
    "DaemonResponse",
    "HookDaemonServer",
    "evaluate_hook_request",
    "send_daemon_request",
]
