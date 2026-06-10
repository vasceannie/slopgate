"""Terminal formatting helpers for lint report output."""

from __future__ import annotations

from typing import cast

from slopgate.lint._baseline import Violation


def colorize(code: str, text: str, enabled: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


def existing_location_lines(violation: Violation, *, color: bool) -> list[str]:
    if "; locations:" in violation.detail:
        return []
    raw_locations = violation.metadata.get("existing_locations")
    if not isinstance(raw_locations, list):
        return []
    locations = [
        item for item in cast("list[object]", raw_locations) if isinstance(item, str)
    ]
    if not locations:
        return []
    location_text = ", ".join(locations)
    raw_more = violation.metadata.get("existing_locations_more")
    if isinstance(raw_more, int) and raw_more > 0:
        location_text += f", ... +{raw_more} more"
    marker = colorize("2", "↳", color)
    return [f"      {marker} existing locations: {location_text}"]
