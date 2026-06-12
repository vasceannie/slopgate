from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hypothesis import given, strategies

from slopgate.config import load_config
from slopgate.constants import METADATA_PATH
from slopgate.context import HookContext
from slopgate.installer.suite import autoupdate_windows
from slopgate.enrichment._helpers import metadata_str, path_source_from_metadata
from slopgate.models import RuleFinding, Severity
from slopgate.state import HookStateStore
from slopgate.trace import TraceWriter
from slopgate.util.payloads import HookPayload

METADATA_KEYS = strategies.text(min_size=1, max_size=12)
METADATA_VALUES = strategies.one_of(
    strategies.text(), strategies.integers(), strategies.none()
)
METADATA_MAPS = strategies.dictionaries(
    METADATA_KEYS,
    METADATA_VALUES,
    max_size=6,
)
FILE_CONTENT = strategies.text(alphabet="abc xyz\n", min_size=1, max_size=30)


def _context_for_root(root: Path) -> HookContext:
    config = load_config(root=root, ensure_enrollment=False, ensure_trace=False)
    trace = TraceWriter(root / ".slopgate" / "trace")
    return HookContext(
        payload=HookPayload({"tool_input": {}}, config),
        config=config,
        trace=trace,
        state=HookStateStore(trace.trace_dir),
    )


def _load_source_from_temp_root(content: str) -> tuple[Path, str] | None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        target = root / "sample.py"
        target.write_text(content, encoding="utf-8")
        finding = RuleFinding(
            rule_id="RULE",
            title="title",
            severity=Severity.LOW,
            metadata={METADATA_PATH: "sample.py"},
        )
        return path_source_from_metadata(finding, _context_for_root(root))


@given(METADATA_MAPS, METADATA_KEYS)
def test_metadata_str_returns_only_nonempty_strings(
    metadata: dict[str, object], key: str
) -> None:
    result = metadata_str(metadata, key)

    assert result is None or result == metadata[key], (
        "metadata_str should return only the keyed nonempty string value"
    )


@given(FILE_CONTENT)
def test_path_source_from_metadata_loads_existing_relative_paths(
    content: str,
) -> None:
    loaded = _load_source_from_temp_root(content)

    assert loaded is not None and loaded[1] == content, (
        "path_source_from_metadata should load file content from metadata paths"
    )


@given(strategies.booleans())
def test_remove_windows_task_by_name_decision_table(
    dry_run: bool,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1)

    with patch.object(autoupdate_windows.subprocess, "run", fake_run):
        removed = autoupdate_windows.remove_windows_task_by_name(dry_run=dry_run)

    assert removed is False, "Missing Windows task should return False"
    assert calls == [["schtasks", "/Query", "/TN", "Slopgate Auto Update"]], (
        "Missing Windows task should only run the query command"
    )
