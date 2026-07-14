"""Public formatter for lint detail blocks."""

from __future__ import annotations

from slopgate.lint._baseline import Violation
from slopgate.lint._details.metadata import location, metadata_lines, signature
from slopgate.lint._details.prognosis import prognosis
from slopgate.lint._details.test_context import test_context_lines


def format_violation_details(
    rule_name: str,
    violation: Violation,
    *,
    status: str,
) -> list[str]:
    """Return an extended, prescriptive block for one lint violation."""

    lines = [
        f"    [{status}] {rule_name}",
        f"    file: {violation.relative_path}",
        f"    location: {location(violation)}",
        f"    signature: {signature(rule_name, violation)}",
    ]
    if violation.detail:
        lines.append(f"    detail: {violation.detail}")
    lines.append(f"    stable-id: {violation.stable_id}")
    lines.extend(metadata_lines(violation.metadata))
    lines.extend(test_context_lines(rule_name, violation))
    lines.extend(prognosis(rule_name, violation))
    return lines
