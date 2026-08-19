---
name: test-smells
description: "Skill for the Test_smells area of slopgate. 100 symbols across 9 files."
---

# Test_smells

100 symbols | 9 files | Cohesion: 75%

## When to Use

- Working with code in `src/`
- Understanding how dotted_name, call_tail, iter_tests work
- Modifying test_smells-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/lint/_detectors/test_smells/_production_symbols.py` | integration_test_reference_tokens, add_import_from_reference_tokens, add_import_reference_tokens, reference_tokens_for_node, reference_tokens_for_tree (+15) |
| `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | cast_target_name, is_low_risk_cast_target, is_high_risk_cast_target, is_high_risk_simple_namespace, assigned_names (+12) |
| `src/slopgate/lint/_detectors/test_smells/_basic_detection.py` | call_assertion_name, is_assertion_call, with_item_raises, has_assertion, detect_assertion_free_tests (+10) |
| `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | dotted_name, call_tail, iter_tests, is_call_only_mock_assert, contains_mock_setup (+8) |
| `src/slopgate/lint/_detectors/test_smells/coverage.py` | coverage_rel_path, coverage_percent_from_summary, coverage_percent_from_json_file, _xml_source_roots, _coverage_xml_rel_paths (+6) |
| `src/slopgate/lint/_detectors/test_smells/_hypothesis_obsolete.py` | _project_module_path_exists, missing_import_from_violation, module_or_package_exists, missing_import_violations, missing_production_imports (+4) |
| `src/slopgate/lint/_detectors/test_smells/_payload_detectors.py` | detect_mock_theater, schema_bypass_violation_for_call, detect_schema_bypasses, detect_hand_built_test_payloads, detect_mocked_integration_tests (+1) |
| `src/slopgate/lint/_detectors/test_smells/production_detectors.py` | detect_untested_production_code, detect_missing_integration_tests, has_token, is_utility_or_trivial_helper, integration_seam_score (+1) |
| `src/slopgate/lint/_detectors/test_smells/_integrity_index.py` | _production_call_sites_from_symbols, _hypothesis_reference_tokens, build_test_integrity_index |

## Entry Points

Start here when exploring this area:

- **`dotted_name`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:140`
- **`call_tail`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:149`
- **`iter_tests`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:153`
- **`is_call_only_mock_assert`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:198`
- **`contains_mock_setup`** (Function) — `src/slopgate/lint/_detectors/test_smells/_assertion_core.py:227`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `dotted_name` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 140 |
| `call_tail` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 149 |
| `iter_tests` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 153 |
| `is_call_only_mock_assert` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 198 |
| `contains_mock_setup` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 227 |
| `has_semantic_assertion` | Function | `src/slopgate/lint/_detectors/test_smells/_assertion_core.py` | 242 |
| `cast_target_name` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 64 |
| `is_low_risk_cast_target` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 70 |
| `is_high_risk_cast_target` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 75 |
| `is_high_risk_simple_namespace` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_core.py` | 179 |
| `detect_mock_theater` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_detectors.py` | 56 |
| `schema_bypass_violation_for_call` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_detectors.py` | 84 |
| `detect_schema_bypasses` | Function | `src/slopgate/lint/_detectors/test_smells/_payload_detectors.py` | 112 |
| `integration_test_reference_tokens` | Function | `src/slopgate/lint/_detectors/test_smells/_production_symbols.py` | 318 |
| `build_test_integrity_index` | Function | `src/slopgate/lint/_detectors/test_smells/_integrity_index.py` | 71 |
| `add_import_from_reference_tokens` | Function | `src/slopgate/lint/_detectors/test_smells/_production_symbols.py` | 265 |
| `add_import_reference_tokens` | Function | `src/slopgate/lint/_detectors/test_smells/_production_symbols.py` | 274 |
| `reference_tokens_for_node` | Function | `src/slopgate/lint/_detectors/test_smells/_production_symbols.py` | 279 |
| `reference_tokens_for_tree` | Function | `src/slopgate/lint/_detectors/test_smells/_production_symbols.py` | 295 |
| `test_reference_tokens` | Function | `src/slopgate/lint/_detectors/test_smells/_production_symbols.py` | 302 |

## Connected Areas

| Area | Connections |
|------|-------------|
| _detectors | 7 calls |

## How to Explore

1. `context({name: "dotted_name"})` — see callers and callees
2. `query({search_query: "test_smells"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
