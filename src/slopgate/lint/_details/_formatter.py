"""Public formatter for lint detail blocks."""

from __future__ import annotations

from slopgate.lint._baseline import Violation
from slopgate.lint._details._metadata import _location, _metadata_lines, _signature
from slopgate.lint._details._prognosis import _prognosis
from slopgate.lint._details._test_context import _test_context_lines

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
        f"    location: {_location(violation)}",
        f"    signature: {_signature(rule_name, violation)}",
    ]
    if violation.detail:
        lines.append(f"    detail: {violation.detail}")
    lines.append(f"    stable-id: {violation.stable_id}")
    lines.extend(_metadata_lines(violation.metadata))
    lines.extend(_test_context_lines(rule_name, violation))
    lines.extend(_prognosis(rule_name, violation))
    return lines
