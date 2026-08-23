---
name: gitnexus-area-enrichment
description: "Skill for the Enrichment area of slopgate. 154 symbols across 18 files."
---

# Enrichment

154 symbols | 18 files | Cohesion: 65%

## When to Use

- Working with code in `src/`
- Understanding how pretool_write_payload, make_sibling_test, write_text work
- Modifying enrichment-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/enrichment/code_enrichers.py` | _base_name, _build_long_params_extras, _decorator_is_dataclass, _grouped_type_hints, _parameter_names (+14) |
| `tests/enrichment/test_01_discover_fixtures_to_pytest003_enrichment.py` | test_loop_assert_regex_does_not_backtrack_on_large_patch, test_still_denies_without_fixtures, test_handles_syntax_error_in_conftest, test_no_conftest_returns_empty, test_caps_at_max (+12) |
| `src/slopgate/enrichment/pytest_enrichers.py` | _first_hit_path, _hit_path_and_fixtures, _resolve_hit_path, enrich_fixture_outside_conftest, _append_fixture_enrichment (+10) |
| `tests/enrichment/test_03_pycode008_enrichment_to_pyexc002_enrichment.py` | _thin_wrapper_reason_with_call_site, test_thin_wrapper_cites_repo_local_call_sites, test_thin_wrapper_lists_boundary_checklist, test_includes_common_exceptions, test_lists_called_functions (+8) |
| `tests/enrichment/test_04_pylog001_enrichment_to_enrichment_constant_index_scope.py` | test_unrelated_quality_rule_does_not_build_constant_index, test_finds_path_config, test_suggests_pathlib_pattern, test_finds_constants_module, test_names_triggered_literals_and_lines (+7) |
| `tests/enrichment/test_03_pytest_enrichers_direct.py` | _context, _enriched_finding, _prepare_fixture_project, _prepare_loop_project, _prepare_test_file (+7) |
| `src/slopgate/enrichment/_helpers.py` | append_enrichment_message, first_target_content, get_parse_count, reset_parse_count, safe_read (+5) |
| `tests/enrichment/test_02_pytest001_enrichment_to_regression_fixtures.py` | test_enrichment_error_swallowed, test_includes_split_tip, test_suggests_creating_conftest, test_suggests_callable_for_callbacks, test_suggests_typeddict_for_dicts (+4) |
| `src/slopgate/enrichment/type_enrichers.py` | _collect_suppressions, _describe_suppression, _suppression_advice, _suppression_description, enrich_type_suppression (+4) |
| `src/slopgate/enrichment/logger_enrichers.py` | _dependency_hints, _dependency_in_pyproject, _dependency_in_requirements, enrich_boundary_logger, _append_dependency_hints (+4) |

## Entry Points

Start here when exploring this area:

- **`pretool_write_payload`** (Function) — `tests/test_enrichment.py:62`
- **`make_sibling_test`** (Function) — `tests/test_enrichment.py:49`
- **`write_text`** (Function) — `tests/test_enrichment.py:27`
- **`make_conftest`** (Function) — `tests/test_enrichment.py:31`
- **`mkdir`** (Function) — `tests/test_enrichment.py:23`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `pretool_write_payload` | Function | `tests/test_enrichment.py` | 62 |
| `make_sibling_test` | Function | `tests/test_enrichment.py` | 49 |
| `write_text` | Function | `tests/test_enrichment.py` | 27 |
| `make_conftest` | Function | `tests/test_enrichment.py` | 31 |
| `mkdir` | Function | `tests/test_enrichment.py` | 23 |
| `finding` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 30 |
| `test_enrich_assertion_roulette_adds_fixture_names_and_split_tip` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 102 |
| `test_enrich_fixture_outside_conftest_suggests_nearest_registry` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 138 |
| `test_enrich_test_loop_adds_fixture_parametrize_and_context` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 82 |
| `test_enrich_test_smells_mentions_fixtures_and_time_utilities` | Function | `tests/enrichment/test_03_pytest_enrichers_direct.py` | 118 |
| `discover_fixtures` | Function | `src/slopgate/enrichment/fixtures.py` | 72 |
| `enrich_fixture_outside_conftest` | Function | `src/slopgate/enrichment/pytest_enrichers.py` | 197 |
| `append_enrichment_message` | Function | `src/slopgate/enrichment/_helpers.py` | 22 |
| `first_target_content` | Function | `src/slopgate/enrichment/_helpers.py` | 30 |
| `enrich_silent_except` | Function | `src/slopgate/enrichment/silent_except.py` | 38 |
| `enrich_type_suppression` | Function | `src/slopgate/enrichment/type_enrichers.py` | 152 |
| `enrich_findings` | Function | `src/slopgate/enrichment/__init__.py` | 139 |
| `get_parse_count` | Function | `src/slopgate/enrichment/_helpers.py` | 63 |
| `reset_parse_count` | Function | `src/slopgate/enrichment/_helpers.py` | 57 |
| `safe_read` | Function | `src/slopgate/enrichment/_helpers.py` | 37 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Enrich_findings → _locked_file` | cross_community | 7 |
| `Enrich_findings → _path_lock_for` | cross_community | 7 |
| `Enrich_test_loop → _decorator_target` | cross_community | 5 |
| `Enrich_test_loop → _is_fixture_target` | cross_community | 5 |
| `Enrich_thin_wrapper → Resolve_path` | cross_community | 4 |
| `Enrich_thin_wrapper → Safe_read` | cross_community | 4 |
| `Enrich_long_method → _block_description` | intra_community | 4 |
| `Enrich_test_loop → Safe_parse` | cross_community | 4 |
| `Enrich_test_loop → _iter_conftest_paths` | cross_community | 4 |
| `Enrich_test_loop → _first_hit_path` | cross_community | 4 |

## How to Explore

1. `context({name: "pretool_write_payload"})` — see callers and callees
2. `query({search_query: "enrichment"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
