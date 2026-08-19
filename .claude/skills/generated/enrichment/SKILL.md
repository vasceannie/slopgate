---
name: enrichment
description: "Skill for the Enrichment area of slopgate. 152 symbols across 18 files."
---

# Enrichment

152 symbols | 18 files | Cohesion: 65%

## When to Use

- Working with code in `src/`
- Understanding how pretool_write_payload, write_text, make_sibling_test work
- Modifying enrichment-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/enrichment/code_enrichers.py` | _find_function_node, _load_target_function, _complexity_delta, _count_complexity_sources, _complexity_breakdown_lines (+14) |
| `tests/enrichment/test_01_discover_fixtures_to_pytest003_enrichment.py` | test_still_denies_without_fixtures, test_loop_assert_regex_does_not_backtrack_on_large_patch, test_no_conftest_returns_empty, test_handles_syntax_error_in_conftest, test_finds_sibling_parametrize (+12) |
| `src/slopgate/enrichment/pytest_enrichers.py` | _project_mentions, _time_utils, _build_test_smell_extras, _first_hit_path, _resolve_hit_path (+9) |
| `tests/enrichment/test_03_pycode008_enrichment_to_pyexc002_enrichment.py` | _thin_wrapper_reason_with_call_site, test_thin_wrapper_cites_repo_local_call_sites, test_thin_wrapper_lists_boundary_checklist, test_lists_called_functions, test_includes_common_exceptions (+8) |
| `tests/enrichment/test_04_pylog001_enrichment_to_enrichment_constant_index_scope.py` | test_identifies_specific_suppression, test_gives_fix_advice_for_arg_type, test_suggests_exact_importable_constant, test_suggests_creating_constants, test_names_triggered_literals_and_lines (+7) |
| `tests/enrichment/test_03_pytest_enrichers_direct.py` | _context, finding, _enriched_finding, _tests_dir, _prepare_loop_project (+7) |
| `tests/enrichment/test_02_pytest001_enrichment_to_regression_fixtures.py` | test_includes_split_tip, test_suggests_creating_conftest, test_detects_freezegun_in_requirements, test_suggests_typeddict_for_dicts, test_suggests_callable_for_callbacks (+4) |
| `src/slopgate/enrichment/_helpers.py` | safe_read, append_enrichment_message, first_target_content, reset_parse_count, get_parse_count (+4) |
| `src/slopgate/enrichment/logger_enrichers.py` | _dependency_hints, _dependency_in_requirements, _dependency_in_pyproject, enrich_boundary_logger, _candidate_logger_path (+4) |
| `src/slopgate/enrichment/type_enrichers.py` | _describe_suppression, _suppression_description, _collect_suppressions, _suppression_advice, enrich_type_suppression (+4) |

## Entry Points

Start here when exploring this area:

- **`pretool_write_payload`** (Function) — `tests/test_enrichment.py:62`
- **`write_text`** (Function) — `tests/test_enrichment.py:27`
- **`make_sibling_test`** (Function) — `tests/test_enrichment.py:49`
- **`mkdir`** (Function) — `tests/test_enrichment.py:23`
- **`make_conftest`** (Function) — `tests/test_enrichment.py:31`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `pretool_write_payload` | Function | `tests/test_enrichment.py` | 62 |
| `write_text` | Function | `tests/test_enrichment.py` | 27 |
| `make_sibling_test` | Function | `tests/test_enrichment.py` | 49 |
| `mkdir` | Function | `tests/test_enrichment.py` | 23 |
| `make_conftest` | Function | `tests/test_enrichment.py` | 31 |
| `finding` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 30 |
| `test_enrich_test_loop_adds_fixture_parametrize_and_context` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 82 |
| `test_enrich_assertion_roulette_adds_fixture_names_and_split_tip` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 102 |
| `test_enrich_test_smells_mentions_fixtures_and_time_utilities` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 118 |
| `test_enrich_fixture_outside_conftest_suggests_nearest_registry` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 138 |
| `safe_read` | Function | `src/slopgate/enrichment/_helpers.py` | 37 |
| `enrich_hardcoded_paths` | Function | `src/slopgate/enrichment/quality_enrichers/_paths.py` | 50 |
| `append_enrichment_message` | Function | `src/slopgate/enrichment/_helpers.py` | 22 |
| `first_target_content` | Function | `src/slopgate/enrichment/_helpers.py` | 30 |
| `enrich_silent_except` | Function | `src/slopgate/enrichment/silent_except.py` | 38 |
| `enrich_type_suppression` | Function | `src/slopgate/enrichment/type_enrichers.py` | 152 |
| `enrich_findings` | Function | `src/slopgate/enrichment/__init__.py` | 139 |
| `reset_parse_count` | Function | `src/slopgate/enrichment/_helpers.py` | 57 |
| `get_parse_count` | Function | `src/slopgate/enrichment/_helpers.py` | 63 |
| `enrich_cyclomatic_complexity` | Function | `src/slopgate/enrichment/code_enrichers.py` | 255 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Enrich_test_loop → _is_fixture_target` | cross_community | 5 |
| `Enrich_test_loop → _decorator_target` | cross_community | 5 |
| `Enrich_test_loop → _first_hit_path` | cross_community | 4 |
| `Enrich_test_loop → Resolve_path` | cross_community | 4 |
| `Enrich_test_loop → _iter_conftest_paths` | cross_community | 4 |
| `Enrich_test_loop → Safe_read` | cross_community | 4 |
| `Enrich_test_loop → Safe_parse` | cross_community | 4 |
| `Enrich_long_params → Resolve_path` | cross_community | 4 |
| `Enrich_long_params → Safe_read` | cross_community | 4 |
| `Enrich_cyclomatic_complexity → Resolve_path` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Quality_enrichers | 10 calls |
| Engine | 1 calls |

## How to Explore

1. `context({name: "pretool_write_payload"})` — see callers and callees
2. `query({search_query: "enrichment"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
