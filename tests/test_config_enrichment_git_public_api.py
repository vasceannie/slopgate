from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, strategies

from vibeforcer.config._discovery import config_dir, detect_root, resolve_config_path
from vibeforcer.config._repo import (
    ensure_worktree_enrollment,
    is_path_skipped,
    is_repo_disabled,
    is_repo_enrolled,
    list_git_worktrees,
    resolve_main_git_repo_root,
    resolve_repo_root,
)
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


def test_resolve_repo_root_finds_quality_gate_ancestor(tmp_path: Path) -> None:
    repo = tmp_path / "myrepo"
    repo.mkdir()
    _ = (repo / "quality_gate.toml").write_text("[quality_gate]\nenabled = true\n", encoding="utf-8")
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)

    assert resolve_repo_root(nested) == repo


def test_resolve_repo_root_returns_none_outside_enrolled_repo(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()

    assert resolve_repo_root(outside) is None


def test_is_repo_enrolled_true_when_quality_gate_present(tmp_path: Path) -> None:
    _ = (tmp_path / "quality_gate.toml").write_text("[quality_gate]\nenabled = true\n", encoding="utf-8")

    assert is_repo_enrolled(tmp_path)


def test_is_repo_enrolled_false_when_quality_gate_absent(tmp_path: Path) -> None:
    assert is_repo_enrolled(tmp_path) is False


def test_is_repo_disabled_true_when_noqualitygate_sentinel_present(tmp_path: Path) -> None:
    _ = (tmp_path / ".noqualitygate").write_text("", encoding="utf-8")

    assert is_repo_disabled(tmp_path)


def test_is_repo_disabled_false_when_no_sentinel(tmp_path: Path) -> None:
    assert is_repo_disabled(tmp_path) is False


def test_is_path_skipped_matches_exact_glob(tmp_path: Path) -> None:
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True)
    target.touch()

    assert is_path_skipped(target, [str(target.resolve())]) is True
    assert is_path_skipped(target, ["/some/other/path"]) is False


def test_resolve_main_git_repo_root_returns_none_outside_git(tmp_path: Path) -> None:
    outside = tmp_path / "nongit"
    outside.mkdir()

    result = resolve_main_git_repo_root(outside)

    assert result is None


def test_list_git_worktrees_returns_empty_outside_git(tmp_path: Path) -> None:
    outside = tmp_path / "nongit"
    outside.mkdir()

    result = list_git_worktrees(outside)

    assert result == []


def test_ensure_worktree_enrollment_returns_none_outside_git(tmp_path: Path) -> None:
    outside = tmp_path / "nongit"
    outside.mkdir()

    result = ensure_worktree_enrollment(outside)

    assert result is None


def test_resolve_config_path_prefers_explicit_env_var(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "myconfig.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("VIBEFORCER_CONFIG", str(cfg))

    result = resolve_config_path()

    assert result == cfg.resolve()


def test_detect_root_prefers_explicit_vibeforcer_root_env_var(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBEFORCER_ROOT", str(tmp_path))

    result = detect_root()

    assert result == tmp_path.resolve()
