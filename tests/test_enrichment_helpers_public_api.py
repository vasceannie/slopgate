from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from tests.test_enrichment_public_api import context_for_source
from slopgate.enrichment._helpers import (
    append_enrichment_message,
    first_target_content,
    get_parse_count,
    relative_path,
    reset_parse_count,
    resolve_path,
    safe_parse,
    safe_read,
)
from slopgate.enrichment.local_context import find_local_call_sites
from slopgate.enrichment.quality_enrichers._magic_numbers import enrich_magic_numbers
from slopgate.enrichment.quality_enrichers._paths import enrich_hardcoded_paths
from slopgate.engine import evaluate_payload
from slopgate.models import RuleFinding, Severity

IRRELEVANT_TEXT = strategies.text(alphabet="abc xyz\n#", max_size=80)


def test_enrichment_helpers_read_target_content(tmp_path: Path) -> None:
    source_path = tmp_path / "module.py"
    source_path.write_text("VALUE = 1\n", encoding="utf-8")
    ctx = context_for_source(tmp_path, "VALUE = 1\n")

    assert {
        "content": first_target_content(ctx),
        "read": safe_read(source_path),
        "missing": safe_read(tmp_path / "missing.py"),
    } == {
        "content": "VALUE = 1\n",
        "read": "VALUE = 1\n",
        "missing": "",
    }


def test_enrichment_helpers_resolve_relative_paths(tmp_path: Path) -> None:
    source_path = tmp_path / "module.py"

    assert {
        "relative": relative_path(source_path, tmp_path),
        "resolved": resolve_path("module.py", tmp_path),
    } == {
        "relative": "module.py",
        "resolved": source_path.resolve(),
    }


def test_enrichment_helpers_parse_and_append_messages() -> None:
    item = RuleFinding("rule", "rule", Severity.MEDIUM, message="base\n")

    reset_parse_count()
    parsed = safe_parse("VALUE = 1\n")
    invalid = safe_parse("def broken(:\n")
    append_enrichment_message(item, ["\nextra", "detail"])

    assert {
        "parsed": type(parsed).__name__,
        "invalid": invalid,
        "parse_count": get_parse_count(),
        "message": item.message,
    } == {
        "parsed": "Module",
        "invalid": None,
        "parse_count": 2,
        "message": "base\n\nextra\ndetail",
    }


def test_find_local_call_sites_skips_current_and_hidden_files(tmp_path: Path) -> None:
    current = tmp_path / "current.py"
    current.write_text("def wrapper():\n    pass\nwrapper()\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text("value = wrapper()\n", encoding="utf-8")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "consumer.py").write_text("value = wrapper()\n", encoding="utf-8")
    ctx = context_for_source(tmp_path, "")

    citations = find_local_call_sites("wrapper", ctx, current)

    assert citations == ["consumer.py:1: `value = wrapper()`"]


def test_magic_number_enricher_reports_existing_constants(tmp_path: Path) -> None:
    (tmp_path / "constants.py").write_text("RETRY_LIMIT = 3\n", encoding="utf-8")
    source_path = tmp_path / "worker.py"
    source_path.write_text("delay = 3\n", encoding="utf-8")
    ctx = context_for_source(tmp_path, "delay = 3\n")
    item = RuleFinding(
        "magic-number",
        "magic-number",
        Severity.MEDIUM,
        metadata={"file_path": "worker.py"},
    )

    enrich_magic_numbers(item, ctx)

    assert item.message == (
        "\n\nProject constants module found: `constants.py`"
        "\nExact constant match:"
        "\n  RETRY_LIMIT = 3 (constants.py:1)"
        "\n  from constants import RETRY_LIMIT"
        "\nImport the existing constant from the cited path; do not create a duplicate, "
        "alias, or split-literal workaround."
    )


def test_magic_number_hook_response_cites_existing_constant_location(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    (tmp_path / "src" / "constants.py").write_text(
        "PRIMARY_TIMEOUT_MS = 500\n", encoding="utf-8"
    )
    content = (
        "from __future__ import annotations\n\n"
        "def wait(value: int) -> bool:\n"
        "    return value > 500\n"
    )

    result = evaluate_payload(
        {
            "session_id": "constant-location-response",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/worker.py", "content": content},
        },
        platform="claude",
    )

    assert result.output is not None
    response = str(result.output)
    assert "PRIMARY_TIMEOUT_MS = 500 (src/constants.py:1)" in response
    assert "from constants import PRIMARY_TIMEOUT_MS" in response
    assert "split-literal workaround" in response


def test_hardcoded_path_enricher_reports_central_path_config(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "paths.py").write_text(
        "DATA_DIR = '/var/lib/app'\nCACHE_PATH = '/tmp/app-cache'\n",
        encoding="utf-8",
    )
    ctx = context_for_source(tmp_path, "open('/tmp/app-cache')\n")
    item = RuleFinding("hardcoded-path", "hardcoded-path", Severity.MEDIUM)

    enrich_hardcoded_paths(item, ctx)

    assert item.message == (
        "\n\nPath configuration found in `src/paths.py`:"
        "\n  DATA_DIR = '/var/lib/app'"
        "\n  CACHE_PATH = '/tmp/app-cache'"
    )


@given(IRRELEVANT_TEXT)
def test_magic_number_enricher_has_generic_fallback_property(source: str) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source)
        item = RuleFinding("magic-number", "magic-number", Severity.MEDIUM)
        enrich_magic_numbers(item, ctx)
    assert item.message == (
        "\n\nDefine repeated literals in a constants/config module "
        "instead of inline magic values. Do not split or concatenate "
        "literal fragments to bypass the gate."
    )


@given(IRRELEVANT_TEXT)
def test_hardcoded_path_enricher_has_generic_fallback_property(source: str) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source)
        item = RuleFinding("hardcoded-path", "hardcoded-path", Severity.MEDIUM)
        enrich_hardcoded_paths(item, ctx)
    assert item.message == (
        "\n\nNo central path config found. Consider defining paths in a config module "
        "or using environment variables."
    )
