---
name: scripts
description: "Skill for the Scripts area of slopgate. 102 symbols across 15 files."
---

# Scripts

102 symbols | 15 files | Cohesion: 94%

## When to Use

- Working with code in `bundle/`
- Understanding how smells_from_functions, function_signature, significant_body work
- Modifying scripts-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | function_signature, significant_body, normalized_body_hash, is_thin_wrapper, param_names (+18) |
| `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/code_smell_radar.py` | _preview_locations, _thin_wrapper_smell, _feature_envy_smell, _single_function_smells, _duplicate_body_smells (+8) |
| `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | parse_pyrefly, parse_biome_json, parse_clippy_json, categorize_python_issue, categorize_ts_issue (+4) |
| `bundle/shared/skills/slopgate-test-extender/scripts/find_fixtures.py` | find_conftest_files, find_test_files, extract_fixture_info, analyze_conftest, find_fixture_usage (+3) |
| `bundle/shared/skills/slopgate-code-hygiene-refactor/scripts/analyze_violations.py` | load_baselines, parse_violation, print_summary, print_by_file, print_actionable (+2) |
| `bundle/shared/skills/slopgate-code-hygiene-refactor/scripts/find_similar_functions.py` | normalize_ast, extract_functions, similarity_ratio, find_python_files, find_duplicates (+2) |
| `bundle/shared/skills/slopgate-test-extender/scripts/analyze_tests.py` | find_test_files, analyze_test_function, get_decorator_names, analyze_file, find_similar_tests (+1) |
| `bundle/shared/skills/slopgate-code-hygiene-refactor/scripts/find_constants.py` | find_python_files, find_constant_assignments, find_final_annotations, search_constants, main |
| `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/slopgate_code_smell_history.py` | parse_args, iter_jsonl, pick_path, summarize, main |
| `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/utility_inventory.py` | parse_args, filter_items, print_text, main |

## Entry Points

Start here when exploring this area:

- **`smells_from_functions`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/code_smell_radar.py:192`
- **`function_signature`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py:129`
- **`significant_body`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py:183`
- **`normalized_body_hash`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py:195`
- **`is_thin_wrapper`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py:205`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `smells_from_functions` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/code_smell_radar.py` | 192 |
| `function_signature` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 129 |
| `significant_body` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 183 |
| `normalized_body_hash` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 195 |
| `is_thin_wrapper` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 205 |
| `param_names` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 221 |
| `feature_envy` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 230 |
| `parse_pyrefly` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 42 |
| `parse_biome_json` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 68 |
| `parse_clippy_json` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 109 |
| `categorize_python_issue` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 155 |
| `categorize_ts_issue` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 176 |
| `categorize_rust_issue` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 187 |
| `build_indices` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 196 |
| `parse_directory` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 210 |
| `main` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 241 |
| `is_secretish` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 82 |
| `iter_source_files` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 89 |
| `relpath` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 111 |
| `scan_text_like` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 394 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Is_secretish` | cross_community | 4 |
| `Main → Relpath` | cross_community | 4 |
| `Main → Target_name` | cross_community | 4 |
| `Main → Categories_for_name` | cross_community | 4 |

## How to Explore

1. `context({name: "smells_from_functions"})` — see callers and callees
2. `query({search_query: "scripts"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
