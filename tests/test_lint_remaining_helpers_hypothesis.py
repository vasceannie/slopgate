"""Hypothesis references for remaining incremental helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hypothesis import assume, given, strategies

from slopgate.lint._collector_groups.incremental import restrict_violations
from slopgate.lint._collector_groups.incremental_cache import cached_run_results
from slopgate.lint._collector_groups.planner import LintExecutionPlan
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._collector_groups.runner_specs import cli_collector_specs
from slopgate.lint._collector_groups.scheduling import active_collector_ids
from slopgate.lint._helpers.parallel import (
    parse_attempt_job,
    parse_attempts_parallel,
    should_parse_in_parallel,
)
from slopgate.lint.project_index.assemble import (
    block_violations,
    call_sequence_violations,
    clone_violations,
)
from slopgate.lint.project_index.cache_trust import cache_path_is_trusted
from slopgate.lint._collector_groups.source_prepare import (
    maybe_literals,
    maybe_oversized,
    parsed_groups,
    project_scope_hits,
)
from slopgate.lint._parse_errors import detect_python_parse_errors
from slopgate.lint.project_index.constant_cache import load_constant_index, save_constant_index
from slopgate.lint.project_index.dirty import untracked_python_paths
from slopgate.lint.project_index.fact_filter import fact_type_filter, wanted_fact_type
from slopgate.lint.project_index.integrity_store import (
    index_content_signature,
    load_or_build_integrity_index,
    save_integrity_index,
)
from slopgate.lint.project_index.summarize import (
    attempt_lookup,
    index_root,
    sorted_project_paths,
    summarize_project_file,
    summary_payload_size,
)
from slopgate.models import RegexRuleConfig


@dataclass(frozen=True, slots=True)
class _ActiveCollectorConfig:
    project_root: Path
    enabled_cli_rules: dict[str, bool]


def _custom_rule_membership(
    rule_id: str,
    *,
    enabled: bool,
) -> bool:
    with TemporaryDirectory() as raw_path:
        config = _ActiveCollectorConfig(Path(raw_path), {rule_id: enabled})
        rule = RegexRuleConfig(
            rule_id=rule_id,
            title="Generated rule",
            target="content",
        )

        def configured_rules(_root: Path) -> tuple[RegexRuleConfig, ...]:
            return (rule,)

        with (
            patch("slopgate.lint._config.get_config", lambda: config),
            patch(
                "slopgate.lint._regex_rules.cli_regex_rule_configs",
                configured_rules,
            ),
        ):
            return rule_id in active_collector_ids("cli")


def _cached_result_for_ineligible_plan(
    cache_ready: bool, has_dirty_path: bool
) -> CollectorResults | None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        plan = LintExecutionPlan(
            src_files=(),
            test_files=(),
            dirty_paths=(root / "dirty.py",) if has_dirty_path else (),
            deleted_paths=(),
            active_ids=frozenset(),
            file_local_ids=frozenset(),
            aggregate_ids=frozenset(),
            persist_index=False,
            use_index=True,
            rebuild_index=False,
            build_constants=False,
            surface="cli",
            event=None,
            project_root=root,
            cache_ready=cache_ready,
        )
        return cached_run_results(plan)


@given(strategies.integers(min_value=0, max_value=2))
def test_remaining_helper_names(value: int) -> None:
    assert (
        restrict_violations.__name__,
        cli_collector_specs.__name__,
        parse_attempts_parallel.__name__,
        parse_attempt_job.__name__,
        should_parse_in_parallel.__name__,
        block_violations.__name__,
        call_sequence_violations.__name__,
        clone_violations.__name__,
        sorted_project_paths.__name__,
        parsed_groups.__name__,
        maybe_literals.__name__,
        maybe_oversized.__name__,
        project_scope_hits.__name__,
        attempt_lookup.__name__,
        index_root.__name__,
        summarize_project_file.__name__,
        summary_payload_size.__name__,
        detect_python_parse_errors.__name__,
        load_constant_index.__name__,
        save_constant_index.__name__,
        untracked_python_paths.__name__,
        fact_type_filter.__name__,
        wanted_fact_type.__name__,
        index_content_signature.__name__,
        load_or_build_integrity_index.__name__,
        save_integrity_index.__name__,
        value,
    )[-1] == value


@given(
    rule_id=strategies.from_regex(r"CUSTOM-[A-Z]{1,8}", fullmatch=True),
    enabled=strategies.booleans(),
)
def test_active_collector_ids_respects_custom_rule_enablement_property(
    rule_id: str,
    enabled: bool,
) -> None:
    assert _custom_rule_membership(
        rule_id,
        enabled=enabled,
    ) is enabled


@given(cache_ready=strategies.booleans(), has_dirty_path=strategies.booleans())
def test_cached_run_results_skips_ineligible_plans_property(
    cache_ready: bool, has_dirty_path: bool
) -> None:
    assume(not cache_ready or has_dirty_path)
    assert _cached_result_for_ineligible_plan(cache_ready, has_dirty_path) is None


@given(
    path_parts=strategies.lists(
        strategies.sampled_from(("src", "tmp", "generated", "cache")),
        min_size=1,
        max_size=4,
    )
)
def test_cache_trust_rejects_paths_outside_cache_root_property(
    path_parts: list[str],
) -> None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        assert not cache_path_is_trusted(root, root.joinpath(*path_parts))
