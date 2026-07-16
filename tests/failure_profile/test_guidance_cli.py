from __future__ import annotations

import argparse
import json
import tomllib
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate._argparse_types import SubparserRegistry
from slopgate.cli import main
from slopgate.cli.failure_profile import add_profile_parser, cmd_profile
from slopgate.config import load_config
from slopgate.config._failure_profile import failure_profile_config
from slopgate.engine import evaluate_payload
from slopgate.models import FailureProfileConfig
from slopgate.resources import resource_path
from tests.failure_profile.support import (
    ProfileRepoOptions,
    configure_seeded_guidance_repo,
    configure_profile_repo,
    edit_payload,
    first_write_risk_ids,
)


TODAY = date(2026, 7, 15)


def test_profile_parser_wires_show_to_profile_command() -> None:
    parser = argparse.ArgumentParser()
    sub = cast(SubparserRegistry, parser.add_subparsers(dest="command"))

    add_profile_parser(sub)
    args = parser.parse_args(["profile", "show"])

    assert (args.command, args.profile_action, args.func) == (
        "profile",
        "show",
        cmd_profile,
    ), "Profile parser should route inspection to the profile command"


def test_failure_profile_config_parses_bounded_repo_values() -> None:
    config = failure_profile_config(
        {
            "failure_profile": {
                "enabled": True,
                "retention_days": 14,
                "max_entries": 64,
            }
        }
    )

    assert config == FailureProfileConfig(True, 14, 64), (
        "Repo profile config should parse enablement, retention, and cap"
    )


def test_first_write_guidance_injects_only_top_five_recurring_repo_risks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = configure_seeded_guidance_repo(tmp_path, monkeypatch, TODAY)

    result = evaluate_payload(edit_payload(repo, content="safe"), platform="claude")

    risk_ids = first_write_risk_ids(result)
    assert len(risk_ids) == 5, (
        "First-write preflight should inject only the top five risks"
    )
    assert risk_ids == [
        "RULE-5",
        "RULE-4",
        "RULE-3",
        "RULE-2",
        "RULE-1",
    ], "First-write risk metadata should preserve deterministic profile ranking"


def _run_profile_command(
    capsys: pytest.CaptureFixture[str], repo: Path, action: str
) -> tuple[int, ObjectDict]:
    exit_code = main(["profile", action, "--cwd", str(repo)])
    return exit_code, object_dict(json.loads(capsys.readouterr().out))


def test_profile_show_cli_reports_deterministic_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_profile_repo(tmp_path, monkeypatch)
    _ = evaluate_payload(edit_payload(repo), platform="claude")

    show_exit, shown = _run_profile_command(capsys, repo, "show")

    assert show_exit == 0, "Profile inspection should succeed"
    assert len(object_list(shown["entries"])) == 1, (
        "Profile show should expose the deterministic aggregate snapshot"
    )


@pytest.mark.parametrize(
    "reset_action",
    ("clear", "reset"),
    ids=("clear", "reset_alias"),
)
def test_profile_reset_cli_clears_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reset_action: str,
) -> None:
    repo, _trace_dir = configure_profile_repo(tmp_path, monkeypatch)
    _ = evaluate_payload(edit_payload(repo), platform="claude")

    clear_exit, cleared = _run_profile_command(capsys, repo, reset_action)
    empty_exit, empty = _run_profile_command(capsys, repo, "show")

    assert (clear_exit, empty_exit) == (0, 0), (
        "Profile reset and inspection should succeed"
    )
    assert cleared["status"] == "cleared", "Profile clear should report its action"
    assert object_list(empty["entries"]) == [], "Profile clear should reset the scope"


def test_runtime_config_ignores_global_profile_enablement_without_repo_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "trace_dir": str(tmp_path / "trace"),
                "failure_profile": {
                    "enabled": True,
                    "retention_days": 7,
                    "max_entries": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))

    config = load_config(
        root=repo, repo_root=repo, ensure_enrollment=False, ensure_trace=False
    )

    assert config.failure_profile.enabled is False, "Only repo config may opt in"
    assert config.failure_profile.retention_days == 30, "Old repos keep 30-day defaults"
    assert config.failure_profile.max_entries == 128, "Old repos keep the default cap"


def test_runtime_config_repo_profile_overrides_are_additive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _trace_dir = configure_profile_repo(
        tmp_path, monkeypatch, ProfileRepoOptions(enabled=False)
    )

    config = load_config(
        root=repo, repo_root=repo, ensure_enrollment=False, ensure_trace=False
    )

    assert config.failure_profile.enabled is False, "Profile opt-in should default off"
    assert config.failure_profile.retention_days == 30, (
        "Default retention should be 30 days"
    )
    assert config.failure_profile.max_entries == 32, "Repo cap should parse additively"


def test_slopgate_template_exposes_disabled_profile_defaults() -> None:
    template = tomllib.loads(
        resource_path("slopgate_template.toml").read_text(encoding="utf-8")
    )

    assert object_dict(template["failure_profile"]) == {
        "enabled": False,
        "retention_days": 30,
        "max_entries": 128,
    }, "The public template should expose safe opt-in defaults"
