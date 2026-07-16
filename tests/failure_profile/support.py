"""Shared builders for aggregate failure-profile tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.config import load_config
from slopgate.failure_profile import FailureProfileDimension, FailureProfileStore
from slopgate.models import EngineResult


PROFILE_RULE_ID = "TEST-PROFILE-001"
FIRST_WRITE_RULE_ID = "WORKFLOW-FIRST-WRITE-001"


@dataclass(frozen=True, slots=True)
class ProfileRepoOptions:
    enabled: bool = True
    strict: bool = True
    first_write_action: str | None = None
    cap: int = 32


def configure_profile_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    options: ProfileRepoOptions = ProfileRepoOptions(),
) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "slopgate.toml").write_text(
        (
            f"[slopgate]\nenabled = {str(options.strict).lower()}\n\n"
            "[failure_profile]\n"
            f"enabled = {str(options.enabled).lower()}\n"
            "retention_days = 30\n"
            f"max_entries = {options.cap}\n"
        ),
        encoding="utf-8",
    )
    trace_dir = tmp_path / "trace"
    config: dict[str, object] = {
        "trace_dir": str(trace_dir),
        "regex_rules": [
            {
                "rule_id": PROFILE_RULE_ID,
                "title": "Profile test denial",
                "severity": "HIGH",
                "events": ["PreToolUse"],
                "target": "content",
                "action": "deny",
                "patterns": ["PROFILE_TRIGGER"],
                "path_globs": ["**/*.py"],
                "tool_matchers": ["Edit"],
                "message": "profile test denial",
            }
        ],
    }
    if options.first_write_action is not None:
        config["rule_surfaces"] = {
            FIRST_WRITE_RULE_ID: {"hook": {"action": options.first_write_action}}
        }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
    return repo, trace_dir


def edit_payload(
    repo: Path,
    *,
    content: str = "PROFILE_TRIGGER",
    session_id: str = "session-a",
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "model": "gpt-5.6-sol",
        "provider": "openai",
        "tool_input": {
            "file_path": "src/app.py",
            "old_string": "old",
            "new_string": content,
        },
    }


def profile_payloads(trace_dir: Path) -> tuple[ObjectDict, ...]:
    profile_dir = trace_dir / "failure-profiles"
    return tuple(
        object_dict(json.loads(path.read_text(encoding="utf-8")))
        for path in profile_dir.glob("*.json")
    )


def profile_entries(trace_dir: Path) -> list[ObjectDict]:
    payload = profile_payloads(trace_dir)[0]
    return [object_dict(item) for item in object_list(payload["entries"])]


def profile_scope_ids(trace_dir: Path) -> set[str]:
    return {
        scope_id
        for payload in profile_payloads(trace_dir)
        if (scope_id := string_value(payload.get("scope_id")))
    }


def configure_profile_worktree(tmp_path: Path, repo: Path) -> Path:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "src").mkdir()
    (worktree / "slopgate.toml").write_text(
        (repo / "slopgate.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return worktree


def profile_storage_keys(trace_dir: Path) -> set[str]:
    keys: set[str] = set()
    for payload in profile_payloads(trace_dir):
        keys.update(payload)
        for entry in object_list(payload.get("entries")):
            mapping = object_dict(entry)
            keys.update(mapping)
            keys.update(object_dict(mapping.get("daily_counts")))
    return keys


def configure_seeded_guidance_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    today: date,
) -> Path:
    repo, _trace_dir = configure_profile_repo(
        tmp_path,
        monkeypatch,
        ProfileRepoOptions(first_write_action="context"),
    )
    config = load_config(
        root=repo, repo_root=repo, ensure_enrollment=False, ensure_trace=True
    )
    store = FailureProfileStore(config.trace_dir, repo, config.failure_profile)
    seed_blocked_risks(store, today)
    return repo


def first_write_risk_ids(result: EngineResult) -> list[str]:
    finding = next(
        item for item in result.findings if item.rule_id == FIRST_WRITE_RULE_ID
    )
    return [
        rule_id
        for item in object_list(finding.metadata["aggregate_failure_risks"])
        if (rule_id := string_value(object_dict(item).get("rule_id")))
    ]


def seed_blocked_risks(store: FailureProfileStore, today: date, total: int = 6) -> None:
    for index in range(total):
        store.record(
            FailureProfileDimension(
                rule_id=f"RULE-{index}",
                path_role="source",
                language="python",
                platform="claude",
                model_identifier=None,
                resolution_outcome="blocked",
            ),
            today=today,
            count=index + 2,
        )
