from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, strategies

from vibeforcer.config._discovery import config_dir
from vibeforcer.config._settings import ensure_trace_directories
from vibeforcer.enrichment._types import FixtureInfo, ParametrizeExample
from vibeforcer.enrichment.quality_enrichers._models import (
    ImportableConstant,
    MagicNumberHint,
)
from vibeforcer.models import RuntimeConfig
from vibeforcer.search.git_utils import normalize_clone_url, resolve_add_repo, urls_match


def test_enrichment_metadata_models_preserve_discovered_fields(tmp_path: Path) -> None:
    fixture: FixtureInfo = {"name": "client", "conftest": "tests/conftest.py", "has_params": True}
    example: ParametrizeExample = {"file": "tests/test_app.py", "snippet": "@pytest.mark.parametrize(...)"}
    importable = ImportableConstant("MAX_RETRIES", 3, tmp_path / "constants.py", 12)
    hint = MagicNumberHint("src/service.py", 44, 3)

    assert {
        "fixture": fixture,
        "example": example,
        "importable": importable,
        "hint": hint,
    } == {
        "fixture": {"name": "client", "conftest": "tests/conftest.py", "has_params": True},
        "example": {"file": "tests/test_app.py", "snippet": "@pytest.mark.parametrize(...)"},
        "importable": ImportableConstant("MAX_RETRIES", 3, tmp_path / "constants.py", 12),
        "hint": MagicNumberHint("src/service.py", 44, 3),
    }


def test_ensure_trace_directories_creates_async_trace_tree(tmp_path: Path) -> None:
    config = RuntimeConfig(
        root=tmp_path,
        repo_root=tmp_path,
        trace_dir=tmp_path / "trace",
        prompt_context_files=[],
        search_reminder_message="",
        protected_paths=[],
        sensitive_path_patterns=[],
        system_path_prefixes=[],
        python_ast_enabled=True,
        python_ast_max_parse_chars=1000,
        python_long_method_lines=50,
        python_long_parameter_limit=4,
        post_edit_quality_enabled=False,
        post_edit_quality_block_on_failure=False,
        post_edit_quality_commands={},
        async_jobs_enabled=False,
        async_jobs_commands={},
    )

    ensure_trace_directories(config)

    assert {
        "trace": config.trace_dir.is_dir(),
        "async": (config.trace_dir / "async").is_dir(),
    } == {"trace": True, "async": True}


def test_config_dir_prefers_explicit_environment_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit_config_dir = tmp_path / "config-home"
    monkeypatch.setenv("VIBEFORCER_CONFIG_DIR", str(explicit_config_dir))

    assert config_dir() == explicit_config_dir


@given(strategies.from_regex(r"[A-Za-z0-9_.-]{1,12}/[A-Za-z0-9_.-]{1,12}", fullmatch=True))
def test_git_url_normalization_equates_https_and_ssh_forms(repo_path: str) -> None:
    ssh_url = f"git@github.com:{repo_path}.git"
    https_url = f"https://github.com/{repo_path}"

    assert urls_match(ssh_url, https_url) == (
        normalize_clone_url(ssh_url) == normalize_clone_url(https_url)
    )


def test_git_url_helpers_normalize_and_pass_through_non_local_repo() -> None:
    assert {
        "normalized": normalize_clone_url("https://GitHub.com/Owner/Repo.git"),
        "resolved": resolve_add_repo("https://example.com/org/repo.git"),
    } == {
        "normalized": "github.com/Owner/Repo",
        "resolved": "https://example.com/org/repo.git",
    }
