# Slopgate feedback: untested-public-surface detection is too noisy

## Executive summary

The current `untested-production-code` / `untested-public-api` detector conflates three different quality questions and answers all of them with literal symbol-name matching. In a recent real-world run this produced **214 apparent new violations**, but post-mortem inspection showed that most of them were false positives caused by Slopgate itself rather than by the target codebase.

The four root causes are all inside Slopgate's design:

| Cause                                              | Confidence | Effect                                                                 |
| -------------------------------------------------- | ---------: | ---------------------------------------------------------------------- |
| Slopgate accepts incomplete/stale `coverage.xml`   |  Very high | Falls back to static name matching for every module not in the report  |
| Overbroad public-interface detection               |  Very high | Internal helpers in `_private_module.py` are treated as public API     |
| Baseline identity includes mutable diagnostic text |  Very high | Existing findings appear `NEW` when percentages or symbol lists change |
| No separation of coverage, publicity, and reachability |  High   | One rule tries to do three jobs and fails at all of them               |

This document is feedback for the Slopgate rule engine. The recommended changes are to Slopgate's detector, baseline model, and rule taxonomy—not to downstream projects.

## What the current detector gets wrong

### 1. Too many symbols are classified as public

In Slopgate 1.4.16 the heuristic is essentially:

```py
# src/slopgate/lint/_detectors/test_smells/_production_symbols.py
# public_top_level_defs(), approximately lines 125-135

if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
    if not node.name.startswith("_"):
        results.append(node)
```

A file such as `automation/scripts/eval/execution/_choice_text.py` is therefore treated as a public module surface merely because its functions lack leading underscores:

```py
normalized_choice_text(...)
ellipsized_prefix(...)
choice_value_matches(...)
```

These are active production internals with multiple callers, not stale code or public API. The detector misses the signal from the underscore-prefixed module name.

Slopgate should account for:

* An underscore-prefixed module filename.
* A module's `__all__`.
* Re-exports from the parent package's `__init__.py`.
* Framework registration such as FastAPI route decorators.
* Behavioral tests that enter through a facade and reach internal helpers transitively.

### 2. Static coverage fallback is exact-name matching, not behavioral coverage

When a module is absent from `coverage.xml`, Slopgate falls back to:

```py
# symbol_is_referenced(), approximately lines 333-334

return (
    symbol.name in test_tokens
    or symbol.qualified_name in test_tokens
)
```

This means a test such as:

```py
def test_combobox_execution():
    result = execute_widget_plan(...)
    assert result.selected_value == "United States"
```

does not protect `choice_value_matches()`, even though `execute_widget_plan()` calls it. The helper is reported as untested only because its literal name never appears in test source.

Slopgate should not recommend adding tests whose sole purpose is to name each helper. That creates scanner-gaming tests, not behavior coverage.

### 3. Baseline identity is unstable

`QualityViolation.stable_id()` currently includes the full diagnostic detail:

```py
# src/slopgate/domain.py
# QualityViolation.stable_id(), approximately lines 27-36

return "|".join(
    (
        self.rule_id,
        self.location.file,
        self.signature,
        self.detail,
    )
)
```

For these findings, `detail` contains mutable values such as:

```text
static_test_reference_coverage=0% (0/3 public symbols referenced);
unreferenced=normalized_choice_text, ellipsized_prefix, choice_value_matches;
not present in coverage.xml
```

Any of the following changes produces a new stable ID and therefore a `NEW` violation:

* Coverage changes from 0% to 33%.
* A helper is renamed.
* One helper is added or removed.
* Slopgate switches between static and runtime coverage.
* The ordering of unreferenced symbols changes.

Slopgate should separate identity from mutable metadata.

## Recommended changes to Slopgate

### P0 — Add a coverage-artifact preflight check

Before emitting per-file violations, Slopgate should validate the supplied `coverage.xml`:

```py
def validate_coverage_artifact(
    coverage_path: Path,
    expected_roots: tuple[Path, ...],
) -> CoverageArtifactStatus:
    """Reject incomplete coverage input before emitting per-file violations."""
```

Statuses:

* `coverage_missing`
* `coverage_stale`
* `coverage_incomplete`
* `coverage_complete`

When incomplete, emit one actionable gate failure instead of hundreds of module-level false positives:

```text
coverage-artifact-incomplete:
coverage.xml omits 214 scanned production modules.
Regenerate coverage for the configured source roots.
```

Also ensure `test_support` directories are classified as test roots, not production roots. A configuration such as:

```toml
source_roots = [
    "src",
    "cloud",
    "automation",
    "scripts",
]

test_roots = [
    "tests",
    "test_support",
]
```

should be validated so that test infrastructure does not participate in `untested-production-code`.

### P1 — Make baseline identities semantic and stable

Change `QualityViolation.stable_id()` so diagnostic details are not part of identity:

```py
def stable_id(self) -> str:
    return "|".join(
        (
            self.rule_id,
            self.location.file,
            self.signature,
        )
    )
```

For this rule, use a stable semantic signature:

```py
signature = "module-public-surface-coverage"
```

Avoid encoding mutable percentages or symbol counts:

```py
# Avoid
signature = "coverage-000"
signature = "coverage-033"
```

Keep changing data in metadata:

```py
metadata = {
    "coverage_kind": "static-reference",
    "coverage_percent": 33,
    "referenced_symbols": [...],
    "unreferenced_symbols": [...],
}
```

A regression should update the existing violation rather than create a new identity. Regression tests should cover this:

```py
def test_stable_id_does_not_change_with_coverage_percentage() -> None:
    zero = violation(detail="coverage=0%", coverage_percent=0)
    partial = violation(detail="coverage=33%", coverage_percent=33)

    assert zero.stable_id() == partial.stable_id()


def test_stable_id_changes_when_module_changes() -> None:
    first = violation(file="src/a.py")
    second = violation(file="src/b.py")

    assert first.stable_id() != second.stable_id()
```

A one-time baseline migration will be needed because existing IDs include details.

### P2 — Model public interfaces explicitly

Replace the name-only implementation with an indexed public-surface model:

```py
def public_top_level_defs(
    tree: ast.Module,
    *,
    module_path: Path,
    explicit_exports: frozenset[str] | None,
    package_reexports: frozenset[str],
    framework_entrypoints: frozenset[str],
) -> list[PublicSymbol]:
    ...
```

Recommended precedence:

```py
def is_public_symbol(
    symbol: TopLevelSymbol,
    context: ModuleExportContext,
) -> bool:
    if context.explicit_exports is not None:
        return symbol.name in context.explicit_exports

    if symbol.name in context.framework_entrypoints:
        return True

    if context.module_path.stem.startswith("_"):
        return symbol.name in context.package_reexports

    return not symbol.name.startswith("_")
```

Build a `PublicSurfaceIndex` once per scan:

```py
@dataclass(frozen=True)
class PublicSurfaceIndex:
    explicit_exports_by_module: Mapping[str, frozenset[str]]
    package_reexports_by_module: Mapping[str, frozenset[str]]
    framework_entrypoints_by_module: Mapping[str, frozenset[str]]
```

This cleanly handles:

* `__all__`
* `from ._internal import PublicFacade`
* `_internal.py` modules
* FastAPI `@router.get` / `@router.post`
* Click or Typer commands
* Textual actions and event handlers
* Registered plugin or adapter entrypoints

### P3 — Split into three distinct rules

The current rule conflates distinct conditions. Slopgate should emit three different findings:

#### `untested-public-api`

Use only when a symbol is demonstrably exported or registered as an entrypoint.

Examples:

* Pydantic request/response models intentionally exported by package modules.
* AG-UI event contracts.
* Service facades exported through package `__init__.py`.
* FastAPI route handlers.

#### `possibly-dead-internal`

Use when all are true:

```text
not exported
not framework-registered
no production callers
no runtime coverage
```

This should initially be advisory, because reflection and dynamic registration can defeat static call graphs.

#### `coverage-artifact-incomplete`

Use when the report exists but lacks files expected from configured runtime roots.

This is the actual condition represented by many noisy batch findings.

### P4 — Guide users toward observable contract tests

Slopgate documentation and autofix hints should discourage tests whose only purpose is to import every helper by name. Instead, recommend contract tests for genuine public surfaces:

For Pydantic wire models:

```py
def test_profile_response_serialization_contract() -> None:
    response = ProfileResponse(
        success=True,
        message="ok",
        profile=profile_fixture(),
    )

    payload = response.model_dump(mode="json")

    assert payload["success"] is True
    assert payload["profile"]["personal"]["name"]["first"] == "Travis"
```

For FastAPI routes:

```py
async def test_get_profile_returns_wire_contract(client: AsyncClient) -> None:
    response = await client.get(
        "/api/profile",
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
```

For AG-UI events:

```py
def test_field_verified_event_round_trip() -> None:
    event = FieldVerifiedEvent(
        control_id="country",
        verification_state="passed",
        current_value="United States",
        expected_value="United States",
    )

    restored = decode_event(encode_event(event))

    assert restored == event
```

For internal orchestration helpers, the rule should recommend testing the public entrypoint and relying on runtime coverage to establish that internal branches were exercised.

### P5 — Help users privatize internal helpers consistently

When Slopgate flags internal helpers in private-looking modules, it should suggest privatization rather than testing:

```text
automation/scripts/eval/execution/_choice_text.py
cloud/services/run_metadata/derive_support/_timestamps.py
```

Two acceptable patterns:

**Private implementation module:**

```py
def _normalized_choice_text(...): ...
def _ellipsized_prefix(...): ...
def _choice_value_matches(...): ...
```

**Package-private implementation with a deliberate facade:**

```py
# package/__init__.py
from ._choice_text import choice_value_matches

__all__ = ["choice_value_matches"]
```

The second form means the exported symbol deserves contract coverage. The remaining helpers should remain private and should not be flagged.

## Suggested implementation order for Slopgate

1. **Add coverage-artifact validation** and emit `coverage-artifact-incomplete` as a single gate failure.
2. **Stabilize baseline identity** so `stable_id()` does not include mutable diagnostic text.
3. **Introduce `PublicSurfaceIndex`** and honor `__all__`, re-exports, private module names, and framework entrypoints.
4. **Split the monolithic rule** into `untested-public-api`, `possibly-dead-internal`, and `coverage-artifact-incomplete`.
5. **Re-run Slopgate** against the same target repository to confirm the 214 violations collapse into a small, actionable set.
6. **Use GitNexus only on the remaining `possibly-dead-internal` symbols** to confirm actual reachability.
7. **Update documentation and autofix hints** to recommend privatization or contract testing, not name-in-test coverage.

The gate should ultimately answer three different questions accurately: **Was this production behavior executed? Is this intentionally public? Is this code unreachable?** Slopgate 1.4.16 currently approximates all three using literal symbol references, which turns manageable coverage-quality issues into large batches of false positives.
