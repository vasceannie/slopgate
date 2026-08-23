---
name: gitnexus-area-test-smells
description: "Skill for the Test_smells area of slopgate. 98 symbols across 13 files."
---

# Test_smells

98 symbols | 13 files | Cohesion: 77%

## When to Use

- Working with code in `src/`
- Understanding how touched_integrity_collector_specs, call_tail, contains_mock_setup work
- Modifying test_smells-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/lint/_detectors/test_smells/_production_symbols.py` | symbol_is_referenced, add_import_from_reference_tokens, add_import_reference_tokens, integration_test_reference_tokens, production_test_inputs (+15) |
| `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | assigned_names, assignment_mock_evidence, cast_target_name, contains_token, dict_payload_threshold (+12) |
| `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | call_tail, contains_mock_setup, dotted_name, has_semantic_assertion, is_call_only_mock_assert (+8) |
| `src/slopgate/lint/_detectors/test_smells/coverage.py` | coverage_violation, metadata_int, runtime_coverage_violation, static_coverage_violation, _coverage_xml_rel_paths (+6) |
| `src/slopgate/lint/_detectors/test_smells/_hypothesis_obsolete.py` | detect_hypothesis_candidates, detect_stale_test_references, hypothesis_properties, hypothesis_score, _project_module_path_exists (+4) |
| `src/slopgate/lint/project_index/integrity_facts.py` | _call_tails, _hypothesis_tokens, _import_nodes, attach_integrity_facts, _import_node_hits (+2) |
| `src/slopgate/lint/_detectors/test_smells/_payload_detectors.py` | detect_hand_built_test_payloads, detect_mock_theater, detect_mocked_integration_tests, detect_schema_bypasses, detect_weak_assertions (+1) |
| `src/slopgate/lint/_detectors/test_smells/production_detectors.py` | detect_missing_integration_tests, detect_untested_production_code, _missing_integration_violation, has_token, integration_seam_score (+1) |
| `src/slopgate/lint/_detectors/test_smells/_integrity_index.py` | _hypothesis_reference_tokens, _production_call_sites_from_symbols, build_test_integrity_index |
| `src/slopgate/lint/_collector_groups/integrity_specs.py` | touched_integrity_collector_specs, lazy_integrity_index |

## Entry Points

Start here when exploring this area:

- **`touched_integrity_collector_specs`** (Function) — `src/slopgate/lint/_collector_groups/integrity_specs.py:12`
- **`call_tail`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:149`
- **`contains_mock_setup`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:227`
- **`dotted_name`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:140`
- **`has_semantic_assertion`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:242`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `touched_integrity_collector_specs` | Function | `src/slopgate/lint/_collector_groups/integrity_specs.py` | 12 |
| `call_tail` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 149 |
| `contains_mock_setup` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 227 |
| `dotted_name` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 140 |
| `has_semantic_assertion` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 242 |
| `is_call_only_mock_assert` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 198 |
| `is_weak_assertion` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 211 |
| `iter_tests` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 153 |
| `assigned_names` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 26 |
| `assignment_mock_evidence` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 150 |
| `cast_target_name` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 64 |
| `contains_token` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 119 |
| `dict_payload_threshold` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 94 |
| `integration_mock_evidence` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 163 |
| `is_high_risk_cast_target` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 75 |
| `is_high_risk_simple_namespace` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 179 |
| `is_low_risk_cast_target` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 70 |
| `is_type_narrowing_guard` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 51 |
| `looks_like_deserializer_contract` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 89 |
| `mock_name_is_internal` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 131 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Cli_collector_specs → String_list` | cross_community | 10 |
| `Cli_collector_specs → Load_toml` | cross_community | 10 |
| `Cli_collector_specs → _paths_section` | cross_community | 10 |
| `Cli_collector_specs → Resolve_root_paths` | cross_community | 10 |
| `Cli_collector_specs → _global_enabled_cli_rules` | cross_community | 10 |
| `Cli_collector_specs → _global_surface_cli_rules` | cross_community | 10 |
| `Cli_collector_specs → _repo_enabled_cli_rules` | cross_community | 10 |
| `Cli_collector_specs → _repo_surface_cli_rules` | cross_community | 10 |
| `Cli_collector_specs → _allowlist_values` | cross_community | 10 |
| `Cli_collector_specs → _logging_values` | cross_community | 10 |

## How to Explore

1. `context({name: "touched_integrity_collector_specs"})` — see callers and callees
2. `query({search_query: "test_smells"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
