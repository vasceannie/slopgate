# Control Ops Spec: Slopgate-Native Changed-Test Selection

> Size: M | Owner: Slopgate | Prerequisites: none
> Phase: design-ready implementation spec

## Review Status

Review date: 2026-06-14

Verdict: feasible, with corrections.

The original direction is sound: Slopgate already has enough static test
integrity data to choose likely impacted tests for changed Python source files,
and it can cover JS/TS projects with deterministic path-based test/spec
matching. The implementation should not depend on a repository Makefile. The
command should live inside the Slopgate CLI so hooks, humans, CI, and editor
tasks can all call the same workflow.

Two assumptions from the exploratory draft needed correction:

| Assumption | Correction |
| --- | --- |
| `build_test_integrity_index()` can be called with no arguments and discover all production symbols. | It only falls back to test discovery. Source files must be passed explicitly with `find_source_files()` or production symbols will be empty. |
| `slopgate test` should remain the internal hook smoke-test command. | `slopgate test` should become the operator-facing changed-test workflow. Move the existing internal smoke suite to `slopgate test --smoke`. |

## Objective

Make `slopgate test` the native command for running the tests most likely to be
impacted by changed source files. Python files map to tests that reference their
exported symbols or modules; JS/TS files map to sibling or directly changed
`*.test.*` / `*.spec.*` files, including nested package paths. The command then
either prints those test paths or runs them.

This gives operators a fast local and CI workflow without requiring
project-specific Makefile targets. The first version is a static blast-radius
selector; it is useful for tight feedback loops, but it is not a replacement for
full test suites before releases or broad refactors.

## Non-Goals

- Do not add or require a Makefile target.
- Do not make downstream repositories copy shell snippets to use the feature.
- Do not change Slopgate hook enforcement semantics.
- Do not replace `slopgate lint test-integrity`; this feature reuses some of
  the same facts for a different operator workflow.
- Do not guarantee complete coverage from static token matching alone.

## Key Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Command surface | Use `slopgate test` for changed-test selection and execution. Use `slopgate test --smoke` for the existing internal smoke suite. | The common operator path should get the short command. The internal self-test remains available but becomes explicit. |
| Default input | Default to `--since HEAD` when neither `--since` nor `--files` is provided. | Bare `slopgate test` should give useful feedback for local uncommitted work. |
| Path listing | Use `--list` to print selected test paths without running them. | Avoids an extra `select` subcommand and keeps the command compact for scripts. |
| Makefile usage | Avoid Makefile entirely. | Slopgate can compute git diffs, select tests, and invoke pytest itself. Per-repo wrappers become optional convenience only. |
| Selection basis | Match changed Python production symbols and module names against parsed test reference tokens. Match JS/TS source paths to sibling `test`/`spec` files and changed JS/TS tests to themselves. | Reuses current Python test-integrity indexing where it exists, and uses the repo's Vitest/Jest naming conventions for JS/TS without adding a parser dependency. |
| Source discovery | Build the index with `find_source_files()` and `find_test_files()`. | Current `build_test_integrity_index()` does not discover production files by default. |
| No-match behavior | Exit 0 for no changed Python files or no selected tests. | Empty selection is not itself a test failure. |
| Test runner | Default Python tests to `python -m pytest -n auto -v --tb=short`; default selected JS/TS tests to `npm test -- <package-relative-tests>` from the nearest `package.json`. Keep `--runner` as an override for custom single-runner workflows. | Matches current repo guidance for Python while letting nested JS/TS packages run through their own package scripts. |

## What Already Exists

| Asset | Location | Reuse |
| --- | --- | --- |
| Top-level CLI parser | `src/slopgate/cli/parsers.py` | Currently registers bare `test`; extend this parser with changed-test flags and `--smoke`. |
| CLI command facade | `src/slopgate/cli/commands.py` | Keep `cmd_test` as the public dispatch point for test workflows. |
| Existing smoke command | `src/slopgate/cli/_self_test.py` | Run this only when `slopgate test --smoke` is requested. |
| Test-integrity index | `src/slopgate/lint/_detectors/test_smells/integrity_index.py` | Reuse `IntegrityIndex` and `build_test_integrity_index(...)`; coverage assessment and export facts are built once per holistic scan. |
| Production symbol helpers | `src/slopgate/lint/_detectors/test_smells/production_symbols.py` | Reuse `module_name_from_rel(...)` and `symbol_is_referenced(...)`; export-aware selection lives in `public_symbols.py`. |
| File discovery helpers | `src/slopgate/lint/_helpers/discovery.py` | Reuse `find_source_files()` and `find_test_files()`. |
| Parser smoke tests | `tests/test_cli.py`, `tests/integration/test_cli_parsers_lint.py` | Add focused parser coverage beside existing CLI parser tests. |
| Test-integrity coverage | `tests/test_test_integrity_lint.py` | Reuse fixture style and semantic assertions for selector behavior. |

## Proposed CLI

### Run changed-test workflow

```bash
slopgate test
slopgate test --since HEAD
slopgate test --since origin/main
slopgate test --files src/slopgate/cli/parsers.py src/slopgate/cli/commands.py
```

Execution contract:

- Select test paths first.
- If neither `--since` nor `--files` is provided, behave as
  `slopgate test --since HEAD`.
- If no tests are selected, print a concise message and exit 0.
- Otherwise execute the configured runner with selected test paths appended.
- Default Python runner: `python -m pytest -n auto -v --tb=short`.
- Default JS/TS runner: `npm test -- <package-relative-tests>` from the nearest
  `package.json` for each selected JS/TS test group.
- Arguments after `--` are appended after the selected test paths unless an
  implementation test proves pytest requires a different ordering.

Example:

```bash
slopgate test --since origin/main -- --maxfail=1
```

### Print impacted tests without running them

```bash
slopgate test --list --since HEAD
slopgate test --list --since origin/main
slopgate test --list --files src/slopgate/cli/parsers.py
```

Output contract:

```text
tests/test_cli.py
tests/integration/test_cli_parsers_lint.py
```

Rules:

- Print one relative test path per line, sorted and deduplicated.
- Print nothing and exit 0 when there are no matching tests.
- Accept explicit `--files` paths for editor integrations and hooks.
- Accept `--since REF` for git-based CI/local workflows.
- Reject combined `--since` and `--files` to keep the source of truth explicit.

### Run the internal smoke suite

```bash
slopgate test --smoke
```

This runs the current self-test smoke suite from `src/slopgate/cli/_self_test.py`.
It should not select or run project tests.

## Implementation Scope

| Task | Effort | Notes |
| --- | --- | --- |
| Add selector service module | M | Keep the Python selector in `src/slopgate/cli/changed_tests.py`; keep JS/TS path-based helpers in `src/slopgate/cli/js_ts_tests.py` so the Python integrity-index path remains isolated. |
| Add git changed-file resolver | S | Use `git diff --name-only --diff-filter=AMR <ref>...` from the project root for explicit refs, and plain `HEAD` by default so local uncommitted work is included. For default `HEAD`, also inspect git submodule worktrees and prefix nested changed paths with the submodule path. |
| Build the integrity index correctly | S | Call `build_test_integrity_index(find_source_files(), find_test_files())`. |
| Select matching tests | M | Match changed Python `ProductionSymbol.relative_path`, `symbol_is_referenced(...)`, and module-name tokens. For JS/TS, match changed sources to sibling test/spec files and changed test/spec files to themselves. Deduplicate and sort. |
| Replace test parser semantics | M | Update `slopgate test` flags so changed-test execution is default and `--smoke` invokes the existing internal smoke path. |
| Add test runner execution | S | Use `subprocess.run(...)` without shell execution. Return the subprocess exit code. Split default execution so Python tests use pytest and JS/TS tests use nearest package `npm test`. |
| Add focused tests | M | Cover parser behavior, source discovery, selector matching, no-match output, smoke dispatch, and runner invocation. |

Total effort: M, approximately 3-5 hours.

## Selection Algorithm

Inputs:

- `changed_files`: repository-relative file paths from `--files` or `--since`.
- `IntegrityIndex`: parsed source files, parsed tests, production symbols, and
  reference tokens by test file.

Process:

1. Normalize changed paths to repository-relative POSIX strings.
2. Use Python integrity-index matching for changed Python files.
3. Build `changed_symbols` from `index.production_symbols` where
   `symbol.relative_path` is in `changed_files`.
4. Build `changed_modules` with `module_name_from_rel(path)` for changed Python
   source files.
5. For each test file and token set:
   - Select the test when any changed symbol satisfies
     `symbol_is_referenced(symbol, tokens)`.
   - Select the test when the changed module or a useful module suffix appears
     in the tokens.
6. Add JS/TS tests by path convention:
   - changed `*.test.*` / `*.spec.*` files select themselves;
   - changed JS/TS source files select sibling tests with the same basename and a
     `.test` or `.spec` marker;
   - discovery skips `.git`, `.venv`, `node_modules`, build output, coverage,
     and cache directories.
7. Return sorted relative test paths.

Open design detail: module-token matching must be tested carefully. Current
reference token extraction records full import modules and imported names, but
it does not automatically record every parent module segment for every import.
The first implementation should match exact module tokens and direct imported
symbol tokens, then add suffix or parent-module behavior only with regression
tests proving the need.

## Data and Type Shape

Suggested internal types:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TestSelectionRequest:
    since_ref: str | None
    files: tuple[str, ...]
    list_only: bool
    smoke: bool
    runner: tuple[str, ...]
    runner_args: tuple[str, ...]


@dataclass(frozen=True)
class TestSelectionResult:
    changed_files: tuple[str, ...]
    selected_tests: tuple[str, ...]
```

Keep request parsing separate from selection logic. The selector should be
directly testable without invoking git or pytest.

## Git Diff Behavior

Use a deterministic git helper:

```bash
git diff --name-only --diff-filter=AMR REF...
```

Requirements:

- Run from the discovered project root.
- Return paths relative to that root.
- Include added, modified, and renamed files.
- Exclude deleted files from selection.
- Surface git failures as CLI errors with stderr preserved enough to diagnose
  bad refs or non-git directories.
- For the default `--since HEAD` path, use plain `HEAD` so local staged and
  unstaged changes are included.
- For the default `HEAD` path, inspect registered submodules recursively and
  prefix nested changes such as `vendor/widget/src/Button.tsx` so JS/TS tests
  inside submodule worktrees can be selected by the parent command.

Future extension: add `--staged` or `--worktree` only after the initial
`--since` and `--files` paths are proven.

## Test Strategy

### Unit tests

- Selector returns the test file that imports a changed function by name.
- Selector returns the test file that imports a changed module.
- Selector deduplicates tests when multiple changed symbols match the same test.
- Selector maps JS/TS changed files in nested source directories to sibling
  `*.test.*` / `*.spec.*` files.
- Selector maps changed JS/TS test files to themselves.
- Git helper includes default-`HEAD` changes inside registered submodule
  worktrees with parent-relative path prefixes.
- Selector returns an empty tuple when a changed source file has no references.
- Git helper filters deleted files and preserves added/modified/renamed paths.

### CLI parser tests

- Bare `slopgate test` parses as changed-test execution with the default
  `--since HEAD` behavior.
- `slopgate test --smoke` dispatches to the existing self-test smoke command.
- `slopgate test --since HEAD` parses an explicit git comparison.
- `slopgate test --files src/foo.py` parses explicit files.
- `slopgate test --list --files src/foo.py` parses list-only mode.
- Combining `--since` and `--files` exits with parser error.
- Combining `--smoke` with changed-test flags exits with parser error.
- `slopgate test --since HEAD -- --maxfail=1` preserves runner args.

### Integration tests

- Build a temporary mini project with `src/` and `tests/`, then verify selection
  through the real parser and selector service.
- Run command path with a fake runner executable or injected subprocess boundary
  so the test proves command construction without running unrelated tests.
- Keep smoke-command coverage, but update it to use `slopgate test --smoke`.

### Verification commands

Use focused commands during implementation:

```bash
python -m pytest tests/test_cli.py tests/integration/test_cli_parsers_lint.py -n auto -v --tb=short
python -m pytest tests/test_test_integrity_lint.py -n auto -v --tb=short
slopgate lint check
```

If tests involving subprocess ordering or temporary git repositories are flaky
under xdist, isolate only those tests and document the reason in the final
implementation notes.

## Acceptance Criteria

- `slopgate test` runs changed-test selection and execution, defaulting to
  `--since HEAD` when no changed-file source is provided.
- `slopgate test --smoke` runs the existing internal hook smoke suite.
- `slopgate test --list --files <source.py>` prints deterministic relative test
  paths and exits 0.
- `slopgate test --list --files <source.tsx>` prints matching nested JS/TS
  test/spec paths and exits 0.
- `slopgate test --since <ref>` obtains changed files internally; no Makefile or
  shell wrapper is required.
- The test runner command includes `-n auto` by default unless explicitly
  overridden.
- Empty selections do not fail the command.
- Bad refs, invalid argument combinations, and runner failures produce nonzero
  exits.
- Unit and integration tests prove Python symbol/module import matching, JS/TS
  path matching, default JS/TS package execution, and submodule path discovery.
- `slopgate lint check` passes after implementation.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Static token matching misses dynamically referenced tests. | Document as a fast-path selector, not a full-suite replacement; keep full suite guidance for release gates. |
| Private detector imports leak into CLI code. | Prefer importing through the existing `test_smells` facade, or move shared selector facts to a small public lint support module if needed. |
| Existing muscle memory for `slopgate test` changes. | Make `--smoke` explicit in help text and update tests/docs in the same implementation. |
| Pytest argument ordering causes unexpected behavior. | Add command-construction tests and one smoke run against a tiny project. |
| Git diff range syntax surprises users. | Keep `--files` as the deterministic explicit path and document `--since` examples. |
| JS/TS packages use different test scripts. | Use nearest-package `npm test` only for the default path; keep `--runner` for custom single-runner workflows. |

## Recommended First Cut

Implement the smallest useful version:

1. `slopgate test --files ...`
2. `slopgate test --since REF`
3. `slopgate test --list ...`
4. `slopgate test --smoke`

Do not add config files, Makefile wrappers, staged/worktree modes, JSON output,
or coverage-aware selection in the first pass. Those are reasonable follow-ups
once the static selector proves useful.
