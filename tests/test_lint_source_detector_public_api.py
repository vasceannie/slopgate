from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from slopgate.lint._detectors.duplicates import detect_semantic_clones
from slopgate.lint._detectors.exception_safety import (
    detect_broad_except_swallow,
    detect_silent_except,
    detect_silent_fallback,
)
from slopgate.lint._detectors.logging_conventions import detect_boundary_logging
from slopgate.lint._detectors.source_interop import (
    detect_dead_code,
    detect_feature_envy,
    detect_flat_sibling_files,
    detect_import_aliases,
    detect_import_fanout,
    detect_private_import_chains,
)
from slopgate.lint._detectors.type_safety import (
    detect_any_usage,
    detect_type_suppressions,
)
from slopgate.lint._helpers import ParsedFile, parse_files
from slopgate.lint._config import load_config, reset_config

IDENTIFIERS = strategies.from_regex(r"[a-z][a-z_]{0,12}", fullmatch=True)


def parsed_file(
    tmp_path: Path, source: str, name: str = "sample.py"
) -> list[ParsedFile]:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return parse_files([path])


def parsed_temp_source(source: str, name: str = "sample.py") -> list[ParsedFile]:
    with TemporaryDirectory() as raw_path:
        return parsed_file(Path(raw_path), source, name)


def test_semantic_clone_detector_reports_structurally_identical_functions(
    tmp_path: Path,
) -> None:
    parsed = parsed_file(
        tmp_path,
        """
def alpha(value: int) -> int:
    result = value + 1
    total = result * 2
    final = total - 3
    adjusted = final + 4
    return adjusted

def beta(item: int) -> int:
    result = item + 1
    total = result * 2
    final = total - 3
    adjusted = final + 4
    return adjusted
""".lstrip(),
    )

    violations = detect_semantic_clones(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("semantic-clone", "alpha"),
        ("semantic-clone", "beta"),
    ]


def test_broad_except_detector_reports_swallowed_default_return(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
def swallow() -> list[str]:
    try:
        return load()
    except Exception:
        return []
""".lstrip(),
    )

    violations = detect_broad_except_swallow(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("broad-except-swallow", "swallow")
    ]


def test_silent_fallback_detector_reports_datetime_now_return(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
from datetime import datetime

def fallback():
    try:
        return parse()
    except ValueError:
        return datetime.now()
""".lstrip(),
    )

    violations = detect_silent_fallback(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("silent-datetime-fallback", "fallback")
    ]


def test_silent_except_detector_reports_empty_broad_handler(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
def silent() -> None:
    try:
        run()
    except Exception:
        pass
""".lstrip(),
    )

    violations = detect_silent_except(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("silent-except", "silent"),
    ]


def test_type_safety_detectors_report_any_and_comment_suppressions(
    tmp_path: Path,
) -> None:
    parsed = parsed_file(
        tmp_path,
        """
from typing import Any

def transform(value: dict[str, Any]) -> Any:
    return value  # type: ignore[return-value]
""".lstrip(),
    )

    violations = [*detect_any_usage(parsed), *detect_type_suppressions(parsed)]

    assert [(item.rule, item.identifier) for item in violations] == [
        ("banned-any", "import-Any"),
        ("banned-any", "transform"),
        ("banned-any", "transform"),
        ("type-suppression", "line-4"),
    ]


def test_feature_envy_detector_reports_external_object_dominance(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    parsed = parsed_file(
        tmp_path,
        """
def render(order):
    customer = account.customer.name
    total = account.invoice.total
    status = account.state.value
    return f"{customer}:{total}:{status}"
""".lstrip(),
    )

    violations = detect_feature_envy(parsed)
    reset_config()

    assert [(item.rule, item.identifier) for item in violations] == [
        ("feature-envy", "render")
    ], "Expected feature-envy detector to match PY-CODE-012 repository scans"


def test_dead_code_detector_reports_unreachable_statement(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
def choose() -> int:
    return 1
    value = 2
    return value
""".lstrip(),
    )

    violations = detect_dead_code(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("dead-code", "choose")
    ], "Expected dead-code detector to match PY-CODE-016 repository scans"


def test_flat_sibling_detector_reports_prefix_file_sprawl(tmp_path: Path) -> None:
    load_config(tmp_path)
    src = tmp_path / "src" / "pkg"
    parsed = [
        *parsed_file(tmp_path, "VALUE = 1\n", "src/pkg/agent_core.py"),
        *parsed_file(tmp_path, "VALUE = 1\n", "src/pkg/agent_state.py"),
        *parsed_file(tmp_path, "VALUE = 1\n", "src/pkg/agent_tools.py"),
    ]

    violations = detect_flat_sibling_files(parsed)
    reset_config()

    assert [(item.rule, item.identifier) for item in violations] == [
        ("flat-sibling-files", "agent")
    ], f"Expected flat sibling detector to scan {src}"


def test_boundary_logging_detector_reports_unlogged_event_boundary(
    tmp_path: Path,
) -> None:
    parsed = parsed_file(
        tmp_path,
        """
def publish_user_created(event):
    bus.publish(event)
""".lstrip(),
        "src/events/publisher.py",
    )

    violations = detect_boundary_logging(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("boundary-logging", "publish_user_created")
    ], "Expected boundary logging detector to match PY-LOG-002 repository scans"


def test_boundary_logging_detector_ignores_logged_boundary(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
def publish_user_created(event):
    logger.info("publishing user event", extra={"event": event.name})
    bus.publish(event)
""".lstrip(),
        "src/events/publisher.py",
    )

    assert detect_boundary_logging(parsed) == [], (
        "Logged event boundaries should not produce PY-LOG-002 CLI findings"
    )


def test_import_fanout_detector_reports_large_from_import(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
from package.module import one, two, three, four, five, six, seven, eight, nine
""".lstrip(),
    )

    violations = detect_import_fanout(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("import-fanout", "package.module")
    ], "Expected import fanout detector to match PY-IMPORT-001 repository scans"


def test_import_alias_detector_reports_noncanonical_alias(tmp_path: Path) -> None:
    parsed = parsed_file(tmp_path, "import requests as rq\n")

    violations = detect_import_aliases(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("import-alias", "rq")
    ], "Expected import alias detector to match PY-IMPORT-002 repository scans"


def test_private_import_chain_detector_reports_stacked_private_import(
    tmp_path: Path,
) -> None:
    parsed = parsed_file(tmp_path, "from pkg._internal._detail import value\n")

    violations = detect_private_import_chains(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("private-import-chain", "pkg._internal._detail")
    ], "Expected private import detector to match PY-IMPORT-003 repository scans"


@given(IDENTIFIERS)
def test_semantic_clone_detector_ignores_single_function_property(name: str) -> None:
    parsed = parsed_temp_source(f"def {name}() -> int:\n    return 1\n")
    assert detect_semantic_clones(parsed) == []


@given(IDENTIFIERS)
def test_broad_except_detector_ignores_specific_handlers_property(name: str) -> None:
    parsed = parsed_temp_source(
        f"def {name}() -> None:\n"
        "    try:\n"
        "        run()\n"
        "    except ValueError:\n"
        "        return None\n"
    )
    assert detect_broad_except_swallow(parsed) == []


@given(IDENTIFIERS)
def test_silent_fallback_detector_ignores_non_datetime_returns_property(
    name: str,
) -> None:
    parsed = parsed_temp_source(
        f"def {name}() -> int:\n"
        "    try:\n"
        "        return 1\n"
        "    except ValueError:\n"
        "        return 2\n"
    )
    assert detect_silent_fallback(parsed) == []


@given(IDENTIFIERS)
def test_silent_except_detector_ignores_logged_specific_handlers_property(
    name: str,
) -> None:
    parsed = parsed_temp_source(
        f"def {name}() -> None:\n"
        "    try:\n"
        "        run()\n"
        "    except ValueError as exc:\n"
        "        raise RuntimeError('failed') from exc\n"
    )
    assert detect_silent_except(parsed) == []


@given(IDENTIFIERS)
def test_any_usage_detector_ignores_concrete_annotations_property(name: str) -> None:
    parsed = parsed_temp_source(f"def {name}(value: int) -> int:\n    return value\n")
    assert detect_any_usage(parsed) == []


@given(IDENTIFIERS)
def test_type_suppression_detector_ignores_regular_comments_property(name: str) -> None:
    parsed = parsed_temp_source(f"def {name}() -> None:\n    pass  # regular note\n")
    assert detect_type_suppressions(parsed) == []
