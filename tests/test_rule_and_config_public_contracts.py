from __future__ import annotations

import argparse
from pathlib import Path

from slopgate._argparse_types import SubparserRegistry
from slopgate.config import load_config
from slopgate.lint.config_values import build_default_values
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import join_messages

RawFinding = tuple[str, Severity, str | None]


class RecordingSubparsers:
    def __init__(self) -> None:
        self.names: list[str] = []

    def add_parser(
        self,
        name: str,
        **_kwargs: object,
    ) -> argparse.ArgumentParser:
        self.names.append(name)
        return argparse.ArgumentParser(prog=name)


def _rule_findings_from_raw(raw_findings: list[RawFinding]) -> list[RuleFinding]:
    return [
        RuleFinding(rule_id=rule_id, title=rule_id, severity=severity, message=message)
        for rule_id, severity, message in raw_findings
    ]


def test_subparser_registry_protocol_accepts_argparse_like_registry() -> None:
    registry: SubparserRegistry = RecordingSubparsers()

    parser = registry.add_parser("demo", help="demo command")

    assert parser.prog == "demo"


def test_build_default_values_contains_repo_paths_and_quality_thresholds(
    tmp_path: Path,
) -> None:
    values = build_default_values(tmp_path)

    assert {
        "project_root": values["project_root"],
        "src_root": values["src_root"],
        "tests_root": values["tests_root"],
        "max_complexity": values["max_complexity"],
        "logger_variable": values["logger_variable"],
    } == {
        "project_root": tmp_path,
        "src_root": tmp_path / "src",
        "tests_root": tmp_path / "tests",
        "max_complexity": 12,
        "logger_variable": "logger",
    }


def test_runtime_config_loads_hook_guidance_defaults_and_repo_overrides(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "slopgate.toml").write_text(
        """
[hook_guidance]
project_logger_import = "from app.telemetry import logger"
project_logger_usage = "logger.info('event')"
quality_check_command = "uv run pytest -q"
""".lstrip(),
        encoding="utf-8",
    )

    config = load_config(
        root=tmp_path,
        repo_root=tmp_path,
        ensure_enrollment=False,
        ensure_trace=False,
    )

    assert config.hook_project_logger_import == "from app.telemetry import logger"
    assert config.hook_project_logger_usage == "logger.info('event')"
    assert config.hook_quality_check_command == "uv run pytest -q"


def test_join_messages_formats_findings_and_skips_empty_messages() -> None:
    findings = _rule_findings_from_raw(
        [
            ("RULE-1", Severity.HIGH, "blocked"),
            ("RULE-2", Severity.LOW, None),
        ]
    )

    assert join_messages(findings) == "[RULE-1 | HIGH] blocked"
