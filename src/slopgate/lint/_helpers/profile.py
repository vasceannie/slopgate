"""Lint scan phase and collector timing records."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

from slopgate.constants import LINT_PROFILE_TIME_PRECISION


def format_profile_seconds(seconds: float) -> str:
    """Render a duration for `--profile` output."""
    return f"{seconds:.{LINT_PROFILE_TIME_PRECISION}f}s"


@dataclass(slots=True)
class LintProfile:
    """Mutable timing log for one lint scan."""

    phases: dict[str, float] = field(default_factory=dict)
    collectors: dict[str, float] = field(default_factory=dict)
    git_base_line: str | None = None

    def record_phase(self, name: str, seconds: float) -> None:
        """Accumulate wall time for a named scan phase."""
        self.phases[name] = self.phases.get(name, 0.0) + seconds

    def record_collector(self, collector_id: str, seconds: float) -> None:
        """Accumulate wall time for one collector invocation."""
        self.collectors[collector_id] = (
            self.collectors.get(collector_id, 0.0) + seconds
        )

    def lines(self) -> list[str]:
        """Return printable profile rows."""
        rows = ["profile:"]
        for name, seconds in self.phases.items():
            rows.append(f"  {name}: {format_profile_seconds(seconds)}")
        for collector_id, seconds in self.collectors.items():
            rows.append(
                f"  collector {collector_id}: {format_profile_seconds(seconds)}"
            )
        if self.git_base_line is not None:
            rows.append(f"  git-base: {self.git_base_line}")
        return rows


_ACTIVE_PROFILE: ContextVar[LintProfile | None] = ContextVar(
    "slopgate_lint_profile", default=None
)


def bind_lint_profile(profile: LintProfile | None) -> None:
    """Record the active profile for later CLI flushing."""
    if profile is None:
        return
    _ACTIVE_PROFILE.set(profile)


def attach_git_base_profile_line(line: str) -> None:
    """Add git-base HIT/MISS to the bound profile when `--profile` is active."""
    profile = _ACTIVE_PROFILE.get()
    if profile is None:
        return
    profile.git_base_line = line


def flush_lint_profile() -> None:
    """Print bound `--profile` rows and clear the active profile."""
    profile = _ACTIVE_PROFILE.get()
    if profile is None:
        return
    print("\n".join(profile.lines()))
    _ACTIVE_PROFILE.set(None)
