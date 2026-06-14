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
from slopgate.enrichment._helpers import (
    enrichment_root,
    metadata_str,
    path_source_from_metadata,
)
from slopgate.enrichment.code_enrichers import enrich_long_method
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


def _context_for_nested_root(
    root: Path, repo_root: Path, cwd: Path | None = None
) -> HookContext:
    config = load_config(
        root=root,
        repo_root=repo_root,
        ensure_enrollment=False,
        ensure_trace=False,
    )
    trace = TraceWriter(repo_root / ".slopgate" / "trace")
    return HookContext(
        payload=HookPayload({"cwd": str(cwd or root), "tool_input": {}}, config),
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


def test_path_source_from_metadata_prefers_repo_root_for_nested_cwd(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    nested = repo / "packages" / "api"
    target = repo / "src" / "app.py"
    nested.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    finding = RuleFinding(
        rule_id="RULE",
        title="title",
        severity=Severity.LOW,
        metadata={METADATA_PATH: "src/app.py"},
    )

    loaded = path_source_from_metadata(finding, _context_for_nested_root(nested, repo))

    assert loaded == (target.resolve(), "VALUE = 1\n"), (
        "Metadata paths should resolve from repo_root even when hooks run nested"
    )


def test_integration_enrichment_root_prefers_repo_root_for_nested_cwd(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    nested = repo / "packages" / "api"
    nested.mkdir(parents=True)

    ctx = _context_for_nested_root(nested, repo)

    assert enrichment_root(ctx) == repo, (
        "Nested hook cwd contexts should resolve enrichment lookups from repo_root"
    )


def test_integration_enrichment_root_uses_config_root_for_unrelated_repo_root(
    tmp_path: Path,
) -> None:
    isolated_root = tmp_path / "isolated"
    external_repo = tmp_path / "external" / "repo"
    isolated_root.mkdir()
    external_repo.mkdir(parents=True)

    ctx = _context_for_nested_root(isolated_root, external_repo)

    assert enrichment_root(ctx) == isolated_root, (
        "Synthetic isolated contexts should keep enrichment lookups under config root"
    )


def test_integration_enrichment_root_prefers_repo_root_for_runtime_cwd(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    config_root = tmp_path / "config_home"
    repo.mkdir()
    config_root.mkdir()

    ctx = _context_for_nested_root(config_root, repo, cwd=repo)

    assert enrichment_root(ctx) == repo, (
        "Runtime hook cwd inside repo should resolve enrichment lookups from repo_root"
    )


def test_long_method_enricher_uses_config_root_fallback_for_metadata_path(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    config_root = tmp_path / "config_home"
    repo.mkdir()
    config_root.mkdir()
    (config_root / "sample.py").write_text(
        "def long_target() -> None:\n    if True:\n        return None\n",
        encoding="utf-8",
    )
    finding = RuleFinding(
        rule_id="long-method",
        title="title",
        severity=Severity.LOW,
        metadata={METADATA_PATH: "sample.py", "function": "long_target"},
    )

    enrich_long_method(finding, _context_for_nested_root(config_root, repo, cwd=repo))

    assert "Function structure" in (finding.message or ""), (
        "Code enrichers should fall back to config root for metadata-relative files"
    )


def test_long_method_enricher_uses_repo_root_for_metadata_path(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    config_root = tmp_path / "config_home"
    target = repo / "src" / "sample.py"
    config_root.mkdir()
    target.parent.mkdir(parents=True)
    target.write_text(
        "def long_target() -> None:\n    if True:\n        return None\n",
        encoding="utf-8",
    )
    finding = RuleFinding(
        rule_id="long-method",
        title="title",
        severity=Severity.LOW,
        metadata={METADATA_PATH: "src/sample.py", "function": "long_target"},
    )

    enrich_long_method(finding, _context_for_nested_root(config_root, repo, cwd=repo))

    assert "Function structure" in (finding.message or ""), (
        "Code enrichers should resolve metadata-relative files from repo_root"
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
