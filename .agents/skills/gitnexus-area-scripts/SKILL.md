---
name: gitnexus-area-scripts
description: "Skill for the Scripts area of slopgate. 102 symbols across 15 files."
---

# Scripts

102 symbols | 15 files | Cohesion: 94%

## When to Use

- Working with code in `bundle/`
- Understanding how smells_from_functions, feature_envy, function_signature work
- Modifying scripts-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | feature_envy, function_signature, is_thin_wrapper, normalized_body_hash, param_names (+18) |
| `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/code_smell_radar.py` | _duplicate_body_smells, _duplicate_signature_smells, _feature_envy_smell, _is_utility_like_name, _preview_locations (+8) |
| `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | build_indices, categorize_python_issue, categorize_rust_issue, categorize_ts_issue, main (+4) |
| `bundle/shared/skills/slopgate-test-extender/scripts/find_fixtures.py` | analyze_conftest, extract_fixture_info, find_conftest_files, find_duplicate_fixtures, find_fixture_usage (+3) |
| `bundle/shared/skills/slopgate-code-hygiene-refactor/scripts/analyze_violations.py` | load_baselines, main, parse_violation, print_actionable, print_by_file (+2) |
| `bundle/shared/skills/slopgate-code-hygiene-refactor/scripts/find_similar_functions.py` | extract_functions, find_duplicates, find_python_files, find_similar, main (+2) |
| `bundle/shared/skills/slopgate-test-extender/scripts/analyze_tests.py` | analyze_file, analyze_test_function, find_similar_tests, find_test_files, get_decorator_names (+1) |
| `bundle/shared/skills/slopgate-code-hygiene-refactor/scripts/find_constants.py` | find_constant_assignments, find_final_annotations, find_python_files, main, search_constants |
| `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/slopgate_code_smell_history.py` | iter_jsonl, main, parse_args, pick_path, summarize |
| `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/utility_inventory.py` | filter_items, main, parse_args, print_text |

## Entry Points

Start here when exploring this area:

- **`smells_from_functions`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/code_smell_radar.py:192`
- **`feature_envy`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py:230`
- **`function_signature`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py:129`
- **`is_thin_wrapper`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py:205`
- **`normalized_body_hash`** (Function) — `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py:195`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `smells_from_functions` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/code_smell_radar.py` | 192 |
| `feature_envy` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 230 |
| `function_signature` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 129 |
| `is_thin_wrapper` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 205 |
| `normalized_body_hash` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 195 |
| `param_names` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 221 |
| `significant_body` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 183 |
| `build_indices` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 196 |
| `categorize_python_issue` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 155 |
| `categorize_rust_issue` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 187 |
| `categorize_ts_issue` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 176 |
| `main` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 241 |
| `parse_biome_json` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 68 |
| `parse_clippy_json` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 109 |
| `parse_directory` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 210 |
| `parse_pyrefly` | Function | `bundle/shared/skills/slopgate-hygiene-orchestrator/scripts/parse_lints.py` | 42 |
| `call_target` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 172 |
| `categories_for_name` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 255 |
| `class_signature` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 147 |
| `decorator_name` | Function | `bundle/shared/skills/slopgate-code-smell-utility-locator/scripts/_code_smell_scan.py` | 118 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Is_secretish` | intra_community | 4 |
| `Main → Categories_for_name` | cross_community | 4 |
| `Main → Relpath` | cross_community | 4 |
| `Main → Target_name` | cross_community | 4 |
| `Main → _preview_locations` | cross_community | 4 |
| `Main → _signature_tail` | cross_community | 4 |
| `Main → _is_utility_like_name` | cross_community | 4 |
| `Main → _feature_envy_smell` | cross_community | 4 |
| `Main → _thin_wrapper_smell` | cross_community | 4 |
| `Main → Is_secretish` | cross_community | 4 |

## How to Explore

1. `context({name: "smells_from_functions"})` — see callers and callees
2. `query({search_query: "scripts"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
