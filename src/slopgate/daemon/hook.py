"""Engine-backed resident hook daemon handler."""

from __future__ import annotations

from slopgate.cli._claude_retry import claude_team_event_feedback
from slopgate.constants import PLATFORM_CLAUDE, UNKNOWN_VALUE
from slopgate.daemon.protocol import (
    DaemonRequest,
    DaemonResponse,
    UNKNOWN_DAEMON_VALUE,
)
from slopgate.engine import evaluate_payload
from slopgate.util import logger

CLAUDE_TEAM_EVENT_EXIT_CODE = 2


def evaluate_hook_request(request: DaemonRequest) -> DaemonResponse:
    platform = (request.platform or UNKNOWN_VALUE).strip().lower()
    if not request.payload:
        logger.info(
            "hook daemon empty payload noop",
            platform=platform,
            event=request.event or UNKNOWN_DAEMON_VALUE,
        )
        return DaemonResponse(ok=True)
    logger.info(
        "hook daemon evaluate payload",
        platform=platform,
        event=request.event or UNKNOWN_DAEMON_VALUE,
    )
    result = evaluate_payload(request.payload, platform=platform)
    if platform == PLATFORM_CLAUDE:
        feedback = claude_team_event_feedback(result)
        if feedback:
            return DaemonResponse(
                ok=True,
                stderr=feedback.rstrip() + "\n",
                exit_code=CLAUDE_TEAM_EVENT_EXIT_CODE,
            )
    return DaemonResponse(ok=True, output=result.output or {})
