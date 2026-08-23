---
name: gitnexus-area-project-index
description: "Skill for the Project_index area of slopgate. 126 symbols across 30 files."
---

# Project_index

126 symbols | 30 files | Cohesion: 74%

## When to Use

- Working with code in `src/`
- Understanding how build_analysis_index, build_project_index, facts_to_json work
- Modifying project_index-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/lint/project_index/facts.py` | facts_to_json, _count, _mapping_rows, _pair_tuple, _text (+9) |
| `src/slopgate/lint/project_index/store.py` | upsert_file, connect_index, index_db_path, is_file_local_ready, load_file_rows (+9) |
| `src/slopgate/lint/project_index/summarize.py` | _common_parent, attempt_lookup, index_root, sorted_project_paths, summary_payload_size (+8) |
| `src/slopgate/lint/project_index/integrity_store.py` | _payload_from_index, index_content_signature, load_integrity_index, load_or_build_integrity_index, save_integrity_index (+5) |
| `src/slopgate/lint/project_index/constant_cache.py` | _file_signature, _payload_json, load_constant_index, save_constant_index, _constants_from_payload (+3) |
| `src/slopgate/lint/project_index/integrity_facts.py` | _call_sites_from_index, _deprecated_for_refs, _deprecated_hits, _source_modules, _symbols_from_index (+3) |
| `src/slopgate/lint/_collector_groups/source_prepare.py` | build_analysis_index, _constant_index_reusable, _session_constant_index, maybe_literals, _hits_from_facts |
| `src/slopgate/lint/project_index/peek.py` | peek_index, _row_content_matches, _row_current, _row_stat_matches, _stat_mismatched |
| `src/slopgate/lint/project_index/extract.py` | _block_windows, _call_sequences, _numeric_literals, _textual_literals, extract_file_facts |
| `src/slopgate/lint/project_index/fingerprint.py` | _canonical_config_value, _config_payload, _detector_tree_stamp, engine_fingerprint |

## Entry Points

Start here when exploring this area:

- **`build_analysis_index`** (Function) — `src/slopgate/lint/_collector_groups/source_prepare.py:212`
- **`build_project_index`** (Function) — `src/slopgate/lint/project_index/build.py:19`
- **`facts_to_json`** (Function) — `src/slopgate/lint/project_index/facts.py:181`
- **`build_persisted_index`** (Function) — `src/slopgate/lint/project_index/persist.py:19`
- **`upsert_file`** (Function) — `src/slopgate/lint/project_index/store.py:130`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `build_analysis_index` | Function | `src/slopgate/lint/_collector_groups/source_prepare.py` | 212 |
| `build_project_index` | Function | `src/slopgate/lint/project_index/build.py` | 19 |
| `facts_to_json` | Function | `src/slopgate/lint/project_index/facts.py` | 181 |
| `build_persisted_index` | Function | `src/slopgate/lint/project_index/persist.py` | 19 |
| `upsert_file` | Function | `src/slopgate/lint/project_index/store.py` | 130 |
| `attempt_lookup` | Function | `src/slopgate/lint/project_index/summarize.py` | 47 |
| `index_root` | Function | `src/slopgate/lint/project_index/summarize.py` | 35 |
| `sorted_project_paths` | Function | `src/slopgate/lint/project_index/summarize.py` | 23 |
| `summary_payload_size` | Function | `src/slopgate/lint/project_index/summarize.py` | 69 |
| `test_lint_parse_pipeline_integrity_signature_empty_index` | Function | `tests/integration/test_lint_parse_pipeline.py` | 110 |
| `cold_index_context` | Function | `tests/test_lint_incremental_restrict_violations.py` | 14 |
| `test_restrict_violations_passthrough_when_cache_cold` | Function | `tests/test_lint_incremental_restrict_violations.py` | 43 |
| `empty_index` | Function | `tests/test_lint_integrity_facts_api.py` | 26 |
| `test_integrity_index_from_empty_project` | Function | `tests/test_lint_integrity_facts_api.py` | 47 |
| `test_stale_reference_violations_empty` | Function | `tests/test_lint_integrity_facts_api.py` | 51 |
| `test_integrity_index_roundtrip_empty_modules` | Function | `tests/test_lint_integrity_store_api.py` | 31 |
| `incremental_context` | Function | `src/slopgate/lint/_collector_groups/incremental.py` | 22 |
| `apply_index_peek` | Function | `src/slopgate/lint/_collector_groups/planner.py` | 132 |
| `peek_index` | Function | `src/slopgate/lint/project_index/peek.py` | 25 |
| `connect_index` | Function | `src/slopgate/lint/project_index/store.py` | 78 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Source_analysis → Project_root` | cross_community | 10 |
| `Source_analysis → Load_config` | cross_community | 10 |
| `Scan_git_base_debt → Object_dict` | cross_community | 10 |
| `Peek_index → Object_dict` | cross_community | 10 |
| `Source_analysis → Get_quality_scope` | cross_community | 9 |
| `Extract_file_facts → Object_dict` | cross_community | 9 |
| `Scan_git_base_debt → _coerce_path_entries` | cross_community | 8 |
| `Scan_git_base_debt → _resolve_path_entries` | cross_community | 8 |
| `Peek_index → _coerce_path_entries` | cross_community | 8 |
| `Peek_index → _resolve_path_entries` | cross_community | 8 |

## How to Explore

1. `context({name: "build_analysis_index"})` — see callers and callees
2. `query({search_query: "project_index"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
