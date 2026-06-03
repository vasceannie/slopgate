from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from vibeforcer.config import load_config
from vibeforcer.context import HookContext
from vibeforcer.enrichment.code_enrichers import (
    enrich_cyclomatic_complexity,
    enrich_feature_envy,
    enrich_long_method,
    enrich_long_params,
    enrich_thin_wrapper,
)
from vibeforcer.enrichment.logger_enrichers import enrich_stdlib_logger
from vibeforcer.enrichment.silent_except import enrich_silent_except
from vibeforcer.enrichment.type_enrichers import (
    enrich_python_any,
    enrich_type_suppression,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.state import HookStateStore
from vibeforcer.trace import TraceWriter
from vibeforcer.util.payloads import HookPayload


SAMPLE_CODE = """
from dataclasses import dataclass
from service import envied

@dataclass
class UserParams:
    name: str
    email: str

class LocalRecord:
    pass

def long_target(name: str, email: str, age: int, active: bool) -> None:
    first = name.strip()
    second = email.strip()
    third = str(age)
    if active:
        print(first, second, third)

def complex_target(value: int) -> str:
    if value > 10:
        return "large"
    if value > 0:
        return "small"
    return "zero"

def wrapper(value: str) -> str:
    return wrapped(value)

def caller() -> str:
    return wrapper("x")
""".lstrip()

TYPE_AND_EXCEPTION_SOURCE = """
from typing import Any

def handler(payload: dict[str, Any]) -> None:  # type: ignore[arg-type]
    try:
        parse(payload)
        save(payload)
    except Exception:
        pass
""".lstrip()
IRRELEVANT_TEXT = strategies.text(alphabet="abc xyz\n#", max_size=80)


def context_for_source(tmp_path: Path, source: str, path: str = "sample.py") -> HookContext:
    config = load_config(
        root=tmp_path,
        ensure_enrollment=False,
        ensure_trace=False,
    )
    payload = HookPayload(
        {"tool_input": {"file_path": path, "content": source}},
        config,
    )
    trace = TraceWriter(tmp_path / ".vibeforcer" / "trace")
    return HookContext(
        payload=payload,
        config=config,
        trace=trace,
        state=HookStateStore(trace.trace_dir),
    )


def write_sample_code(tmp_path: Path) -> HookContext:
    (tmp_path / "sample.py").write_text(SAMPLE_CODE, encoding="utf-8")
    return context_for_source(tmp_path, SAMPLE_CODE)


def test_long_method_enricher_reports_function_structure(tmp_path: Path) -> None:
    ctx = write_sample_code(tmp_path)
    item = RuleFinding(
        rule_id="long-method",
        title="long-method",
        severity=Severity.MEDIUM,
        metadata={"path": "sample.py", "function": "long_target"},
    )

    enrich_long_method(item, ctx)

    assert item.message == (
        "\n\nFunction structure (potential extraction points):"
        "\n  \u2022 if-block at line 16"
        "\n\nSplit strategy: extract each logical block into a named helper "
        "that does one thing. The parent function becomes an orchestrator."
    )


def test_long_params_enricher_reports_params_and_grouped_type(tmp_path: Path) -> None:
    ctx = write_sample_code(tmp_path)
    item = RuleFinding(
        rule_id="too-many-params",
        title="too-many-params",
        severity=Severity.MEDIUM,
        metadata={"path": "sample.py", "function": "long_target"},
    )

    enrich_long_params(item, ctx)

    assert item.message == (
        "\n\nParameters: `name`, `email`, `age`, `active`"
        "\n\nExisting parameter grouping patterns in this file: `UserParams` (dataclass)"
        "\n\nGroup related parameters into a dataclass or TypedDict:\n"
        "    @dataclass\n"
        "    class Config:\n"
        "        param_a: str\n"
        "        param_b: int\n"
        "        param_c: bool = True"
    )


def test_complexity_enricher_reports_branch_breakdown(tmp_path: Path) -> None:
    ctx = write_sample_code(tmp_path)
    item = RuleFinding(
        rule_id="high-complexity",
        title="high-complexity",
        severity=Severity.MEDIUM,
        metadata={"path": "sample.py", "function": "complex_target"},
    )

    enrich_cyclomatic_complexity(item, ctx)

    assert item.message == "\n\nComplexity breakdown: 2 if/elif branches"


def test_feature_envy_enricher_reports_local_classes_and_import(tmp_path: Path) -> None:
    ctx = write_sample_code(tmp_path)
    item = RuleFinding(
        rule_id="feature-envy",
        title="feature-envy",
        severity=Severity.MEDIUM,
        metadata={"path": "sample.py", "envied_object": "envied"},
    )

    enrich_feature_envy(item, ctx)

    assert item.message == (
        "\n\nClasses in this file: `UserParams`, `LocalRecord`"
        "\n\nImport of `envied`: `from service import envied`"
        "\n\nConsider moving this logic to `envied`'s class as a method, "
        "or restructuring so `envied` exposes a higher-level API."
    )


def test_thin_wrapper_enricher_reports_inline_replacement(tmp_path: Path) -> None:
    ctx = write_sample_code(tmp_path)
    item = RuleFinding(
        rule_id="unnecessary-wrapper",
        title="unnecessary-wrapper",
        severity=Severity.MEDIUM,
        metadata={"path": "sample.py", "function": "wrapper", "wraps": "wrapped"},
    )

    enrich_thin_wrapper(item, ctx)

    assert item.message == (
        "\n\n`wrapper` is called ~1 time(s) in this file."
        "\nReplace each `wrapper(...)` call with `wrapped(...)`, then remove the wrapper."
    )


def test_logger_enricher_reports_project_logging_abstractions(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "logger.py").write_text(
        "def get_logger(name: str) -> object:\n    return object()\n",
        encoding="utf-8",
    )
    ctx = context_for_source(tmp_path, "import logging\n")
    item = RuleFinding(
        rule_id="stdlib-logger",
        title="stdlib-logger",
        severity=Severity.MEDIUM,
    )

    enrich_stdlib_logger(item, ctx)

    assert item.message == (
        "\n\nProject logger found at: `src/logger.py`"
        "\n  Pattern: `def get_logger(name: str) -> object:`"
    )


def test_silent_except_enricher_reports_called_functions(tmp_path: Path) -> None:
    ctx = context_for_source(tmp_path, TYPE_AND_EXCEPTION_SOURCE)
    item = RuleFinding(
        rule_id="silent-except",
        title="silent-except",
        severity=Severity.MEDIUM,
        metadata={"path": "sample.py"},
    )

    enrich_silent_except(item, ctx)

    assert item.message == (
        "\n\nFunctions called in try block: `parse`, `save`"
        "\nCheck what exceptions these functions raise and catch those specifically."
        "\n\nCommon specific exceptions:\n"
        "  \u2022 File I/O: `FileNotFoundError`, `PermissionError`, `IsADirectoryError`\n"
        "  \u2022 Network: `ConnectionError`, `TimeoutError`, `httpx.HTTPError`\n"
        "  \u2022 Parsing: `json.JSONDecodeError`, `ValueError`, `KeyError`\n"
        "  \u2022 Encoding: `UnicodeDecodeError`, `UnicodeEncodeError`"
    )


def test_python_any_enricher_reports_dict_and_callback_guidance(tmp_path: Path) -> None:
    ctx = context_for_source(tmp_path, TYPE_AND_EXCEPTION_SOURCE)
    item = RuleFinding(
        rule_id="python-any",
        title="python-any",
        severity=Severity.MEDIUM,
    )

    enrich_python_any(item, ctx)

    assert item.message == (
        "\n\nTIP: For dict-like structures, consider TypedDict:\n"
        "    class UserData(TypedDict):\n"
        "        name: str\n"
        "        email: str\n"
        "\nTIP: For callbacks/handlers, use Callable with specific signatures:\n"
        "    Callable[[str, int], bool]"
    )


def test_type_suppression_enricher_reports_specific_advice(tmp_path: Path) -> None:
    ctx = context_for_source(tmp_path, TYPE_AND_EXCEPTION_SOURCE)
    item = RuleFinding(
        rule_id="type-suppression",
        title="type-suppression",
        severity=Severity.MEDIUM,
    )

    enrich_type_suppression(item, ctx)

    assert item.message == (
        "\n\nSuppression(s) found: type ignore for `arg-type`"
        "\n  -> `arg-type`: The argument type does not match. "
        "Narrow the input or add an overload."
    )


@given(IRRELEVANT_TEXT)
def test_feature_envy_enricher_ignores_incomplete_metadata_property(source: str) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source)
        item = RuleFinding("feature-envy", "feature-envy", Severity.MEDIUM)
        enrich_feature_envy(item, ctx)
    assert item.message is None


@given(IRRELEVANT_TEXT)
def test_thin_wrapper_enricher_ignores_incomplete_metadata_property(source: str) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source)
        item = RuleFinding("unnecessary-wrapper", "unnecessary-wrapper", Severity.MEDIUM)
        enrich_thin_wrapper(item, ctx)
    assert item.message is None


@given(IRRELEVANT_TEXT)
def test_complexity_enricher_ignores_incomplete_metadata_property(source: str) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source)
        item = RuleFinding("high-complexity", "high-complexity", Severity.MEDIUM)
        enrich_cyclomatic_complexity(item, ctx)
    assert item.message is None


@given(IRRELEVANT_TEXT)
def test_silent_except_enricher_keeps_irrelevant_content_generic_property(
    source: str,
) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source)
        item = RuleFinding("silent-except", "silent-except", Severity.MEDIUM)
        enrich_silent_except(item, ctx)
    assert "Functions called in try block" not in (item.message or "")


@given(IRRELEVANT_TEXT)
def test_python_any_enricher_ignores_irrelevant_content_property(source: str) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source)
        item = RuleFinding("python-any", "python-any", Severity.MEDIUM)
        enrich_python_any(item, ctx)
    assert item.message is None


@given(IRRELEVANT_TEXT)
def test_type_suppression_enricher_ignores_irrelevant_content_property(
    source: str,
) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source)
        item = RuleFinding("type-suppression", "type-suppression", Severity.MEDIUM)
        enrich_type_suppression(item, ctx)
    assert item.message is None
