---
name: python-ast
description: "Skill for the Python_ast area of slopgate. 59 symbols across 7 files."
---

# Python_ast

59 symbols | 7 files | Cohesion: 75%

## When to Use

- Working with code in `src/`
- Understanding how detect_pytest_asyncio_patterns, pytest_aliases, fixture_decorator_call work
- Modifying python_ast-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/rules/python_ast/_pytest_asyncio_ast.py` | _add_module_import_aliases, _add_from_import_aliases, pytest_aliases, fixture_decorator_call, has_async_yield (+14) |
| `src/slopgate/rules/python_ast/_pytest_asyncio_config.py` | _mapping_value, string_value, _addopts_asyncio_mode, _pyproject_config, _ini_config (+5) |
| `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | is_pytest_path, unknown_fixture_scope_message, unknown_loop_scope_message, configured_loop_scope_note, resource_scope_note (+3) |
| `src/slopgate/rules/python_ast/_pytest_asyncio.py` | _check_async_fixtures, _check_source, _check_fixture_loop_scope, _check_async_tests, _is_auto_mode (+2) |
| `src/slopgate/lint/_detectors/test_smells/pytest_asyncio.py` | _pytest_asyncio_config, _violation, _async_test_violations, _fixture_scope_violation, _async_fixture_violations (+1) |
| `src/slopgate/rules/python_ast/_pytest_asyncio_scope.py` | fixture_scope_fragment, is_unknown_fixture_scope, valid_fixture_scope_text, is_valid_fixture_loop_scope, _scope_order |
| `src/slopgate/rules/python_ast/_helpers.py` | _read_candidate_source, _pre_tool_sources, _post_tool_sources, _python_sources_for_context |

## Entry Points

Start here when exploring this area:

- **`detect_pytest_asyncio_patterns`** (Function) — `src/slopgate/lint/_detectors/test_smells/pytest_asyncio.py:110`
- **`pytest_aliases`** (Function) — `src/slopgate/rules/python_ast/_pytest_asyncio_ast.py:34`
- **`fixture_decorator_call`** (Function) — `src/slopgate/rules/python_ast/_pytest_asyncio_ast.py:180`
- **`is_pytest_path`** (Function) — `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py:26`
- **`has_async_yield`** (Function) — `src/slopgate/rules/python_ast/_pytest_asyncio_ast.py:202`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `detect_pytest_asyncio_patterns` | Function | `src/slopgate/lint/_detectors/test_smells/pytest_asyncio.py` | 110 |
| `pytest_aliases` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_ast.py` | 34 |
| `fixture_decorator_call` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_ast.py` | 180 |
| `is_pytest_path` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | 26 |
| `has_async_yield` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_ast.py` | 202 |
| `unknown_fixture_scope_message` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | 38 |
| `unknown_loop_scope_message` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | 46 |
| `configured_loop_scope_note` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | 58 |
| `resource_scope_note` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | 72 |
| `plain_auto_fixture_scope_message` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | 108 |
| `explicit_fixture_loop_scope_message` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | 127 |
| `fixture_scope_fragment` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_scope.py` | 6 |
| `is_unknown_fixture_scope` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_scope.py` | 12 |
| `valid_fixture_scope_text` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_scope.py` | 16 |
| `is_valid_fixture_loop_scope` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_scope.py` | 20 |
| `string_keyword` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_ast.py` | 192 |
| `string_value` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_config.py` | 42 |
| `pytest_config_for_root` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_config.py` | 127 |
| `pytest_asyncio_default_fixture_loop_scope` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_config.py` | 148 |
| `fixture_scope_state` | Function | `src/slopgate/rules/python_ast/_pytest_asyncio_fixture_scope.py` | 89 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Size | 2 calls |
| _rules | 1 calls |
| Duplicate_rules | 1 calls |
| _detectors | 1 calls |

## How to Explore

1. `context({name: "detect_pytest_asyncio_patterns"})` — see callers and callees
2. `query({search_query: "python_ast"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
