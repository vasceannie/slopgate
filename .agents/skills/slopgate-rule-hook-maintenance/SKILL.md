---
name: slopgate-rule-hook-maintenance
description: Maintain Slopgate's own rule engine, hook runtime, adapters, and pattern detectors. Use when creating, updating, fine-tuning, enabling, or testing rules, hooks, adapter behavior, event responses, runtime policies, or pattern-capture logic inside the slopgate repository. This is for Slopgate maintainers only; do not use for bundle distribution skills, Hermes admin work, or downstream project rule authoring.
---

# Slopgate Rule and Hook Maintenance

Use this skill when working inside the `slopgate` repository on Slopgate's own rule engine, hook runtime, platform adapters, installer wiring, runtime policy, or pattern detectors.

This is a maintainer workflow. It is not a bundle-distribution workflow, not a Hermes admin workflow, and not guidance for installing Slopgate into downstream repositories.

## Scope boundaries

Do:

- Create, update, tune, enable, or test rules under `src/slopgate/rules/`.
- Maintain hook runtime commands in `src/slopgate/cli/hook_runtime.py` and `src/slopgate/cli/hook_runtime_parsers.py`.
- Maintain platform adapters under `src/slopgate/adapters/`.
- Maintain installer hook wiring under `src/slopgate/installer/` when the runtime contract changes.
- Maintain daemon hook handling under `src/slopgate/daemon/` when changing resident hook behavior.
- Update tests under `tests/` that prove rule contracts, adapter rendering, hook installation, daemon fallback, and pattern detection.
- Keep README/docs claims aligned with the current platform capabilities.

Do not:

- Put this skill or maintainer-only assets under `bundle/`.
- Treat this as a Hermes skill/admin bundle.
- Scatter Slopgate-branded assets into user-level harness directories such as `~/.claude`, `~/.config/opencode`, or global agent skills.
- Claim Claude/Codex/OpenCode/Cursor parity unless the adapters and upstream hook surfaces prove it.
- Weaken tests, baselines, type checking, lint policy, hook enforcement, or rule thresholds just to make a change pass.

## Maintainer workflow

1. Classify the requested change.
   - New detector/pattern: identify the behavior to catch, the false-positive boundaries, and whether it belongs in regex rules, AST rules, common quality rules, error rules, or adapter normalization.
   - Hook/runtime change: identify which platform events, payload fields, response shapes, exit codes, and installation paths are affected.
   - Adapter change: identify normalized input shape and rendered output shape for each affected platform.
   - Enablement/config change: identify default policy, repo override support, disabled/severity behavior, and migration risk.
2. Investigate existing nearby patterns before editing.
   - Search for similar rule IDs, `RuleFinding` construction, event names, config fields, and tests.
   - Prefer extending existing helpers over creating a parallel path.
   - Before editing functions/classes/methods, follow repository GitNexus impact-analysis rules if GitNexus tools are available. If those tools are unavailable, explicitly state that impact analysis could not be run and proceed with extra-narrow edits.
3. Write or update behavior-locking tests first when practical.
   - Add narrow unit tests for detector positives and negatives.
   - Add adapter/rendering tests when output JSON changes.
   - Add hook runtime or installer tests when event routing or command wiring changes.
4. Implement the smallest behavior change that satisfies the tests.
5. Run targeted validation first, then broader checks if risk warrants it.
6. Update docs only for externally visible behavior, platform capability changes, rule IDs, config fields, or installation semantics.

## Pattern investigation checklist

Before adding or tuning a rule, capture these facts in your reasoning:

- What exact pattern should be caught?
- Is the pattern syntactic, semantic, event-driven, command-driven, path-driven, or output-driven?
- What examples must not be caught?
- Which event(s) provide enough context to detect it?
- Which tool names and payload fields expose the signal?
- Should detection inspect content, paths, shell commands, tool output, session state, or repository config?
- Should the rule deny/block immediately, add advisory context, mutate `updated_input`, or only trace metadata?
- Does the pattern require state across events? If yes, use `HookStateStore`/trace-backed state instead of module globals.
- Does the pattern need platform-specific normalization? If yes, update the adapter rather than duplicating platform logic in the rule.
- Can it be configured or disabled through `slopgate.toml`? If yes, add config loading, public contract tests, and sensible defaults.

Prefer rule placement by signal type:

- General runtime guardrails: `src/slopgate/rules/common/` or existing top-level rule modules.
- Python AST shape/patterns: `src/slopgate/rules/python_ast/` and submodules under `_rules/`.
- Post-edit quality/lint behavior: `src/slopgate/rules/common/quality/`.
- Error/output signal detection: `src/slopgate/rules/error_rules.py` and `_error_output_signals.py`.
- Baseline protection: `src/slopgate/rules/baseline_guard.py`.
- Adapter normalization/rendering: `src/slopgate/adapters/`.

## Rule implementation contract

Rules implement `src/slopgate/rules/base.py`:

- Subclass `Rule`.
- Set `rule_id`, `title`, and `events`.
- Implement `evaluate(ctx: HookContext) -> list[RuleFinding]`.
- Use `rule.supports(ctx.event_name)` semantics by setting `events` precisely. An empty `events` tuple means all events.
- Return an empty list for no finding; do not raise for normal unsupported payloads.
- Keep findings JSON-serializable: `metadata` and `updated_input` must be plain JSON-compatible values.
- Use `is_rule_enabled(ctx, rule_id, default=...)` when the rule has config-controlled enablement.
- Let severity overrides work by setting the default severity on the finding rather than hardcoding policy after evaluation.

`RuleFinding` fields:

- `rule_id`: stable public ID, e.g. `PY-TEST-005` or `QUALITY-LINT-001`.
- `title`: concise human-readable rule title.
- `severity`: `Severity.LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- `decision`: use `deny`, `block`, `ask`, `allow`, or `None` according to event/platform semantics.
- `message`: short direct reason; this is used in denial reasons.
- `additional_context`: remediation guidance or advisory context.
- `updated_input`: only when the platform supports safe input mutation.
- `metadata`: stable diagnostic data for tests, traces, and dashboards.

Decision guidance:

- Use `deny` for `PreToolUse`/permission-style hard prevention where the platform can stop the action.
- Use `block` for events rendered as stop/post/prompt blocking where adapters map it to platform-native blocking.
- Use `ask` only when the platform can route to user confirmation.
- Use `allow` only when intentionally allowing with `updated_input` or explicit permission semantics.
- Use `None` plus `additional_context` for advisory guidance that should not interrupt execution.

## Hook event and adapter guidance

Canonical events and constants live in `src/slopgate/constants.py`:

- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `Stop`
- Other adapter-supported events such as `UserPromptSubmit`, `SessionStart`, `SubagentStart`, `SubagentStop`, `ConfigChange`, and `PostToolUseFailure`.

The engine path is:

1. `src/slopgate/cli/hook_runtime.py` reads hook JSON from stdin.
2. `evaluate_payload()` gets the platform adapter from `src/slopgate/adapters/`.
3. The adapter normalizes platform payload fields into canonical Slopgate payloads.
4. `build_context()` builds `HookContext`.
5. `run_rules()` evaluates always-on and repo-strict rules according to enforcement mode.
6. Findings are enriched, deduplicated, rendered through the adapter, traced, and emitted as JSON.

Adapter responsibilities:

- Normalize platform-specific event names, session IDs, cwd fields, tool names, tool input, and tool output.
- Render Slopgate findings into platform-native hook responses.
- Keep platform limitations explicit instead of pretending parity.

Current platform capability expectations:

- Claude is the reference/full hook surface.
- Codex is partial and currently Bash-focused/experimental compared with Claude-style tool parity.
- OpenCode is degraded through plugin event translation; prompt interception is unavailable, stop blocking is advisory, and post-tool deny is best-effort.
- Cursor support is partial; post-tool/after-edit paths cannot hard-block in the same way and may inject context only.

When changing adapter output, update tests for the affected adapter and at least one engine-level path that proves `render_output()` selects the expected top decision and context.

## Event response guidance

Rendering is centralized in `src/slopgate/engine/_render.py` and adapters.

General behavior:

- The top decision is selected by decision strength and severity.
- `deny` and `block` outrank `ask`, then `allow`, then advisory-only findings.
- `additional_context` from immediate findings is shown first; unrelated advisory context is separated as later design debt.
- `updated_input` from findings is merged in order.

Claude response expectations:

- `PreToolUse` and `SubagentStart`: render `hookSpecificOutput` with `permissionDecision`, `permissionDecisionReason`, optional `updatedInput`, and optional `additionalContext`.
- `PermissionRequest`: render hook-specific `decision.behavior`, mapping `block` to `deny`.
- `UserPromptSubmit` and `PostToolUse`: render `decision: block` plus `reason` for blocking decisions, and hook-specific additional context when present.
- `Stop`, `SubagentStop`, and `ConfigChange`: render blocking `decision/reason`, or `systemMessage` for advisory-only context.
- `SessionStart`: render hook-specific additional context only.

OpenCode response expectations:

- `PreToolUse`: render `{action: block, reason}` for blocking decisions, `{action: allow, updated_args}` for allowed mutations, or `{action: context, context}` for advisory context.
- `PermissionRequest`: render block/allow according to decision and updated args.
- `PostToolUse`: blocking is best-effort; include context when present.
- `Stop`: render `{action: continue, reason}` for block/deny/ask or context-only output for advisory guidance.

Do not encode platform response JSON inside individual rules. Rules should return `RuleFinding`; adapters render the response.

## Hook runtime and installer guidance

Runtime command files:

- `src/slopgate/cli/hook_runtime.py`: `handle`, `daemon`, `handle-async`, replay behavior, daemon fallback, exit-code semantics.
- `src/slopgate/cli/hook_runtime_parsers.py`: CLI parser registration and argument validation.
- `src/slopgate/daemon/hook.py`: daemon-side hook request evaluation.
- `src/slopgate/installer/hook_proxy.py`: POSIX daemon proxy command generation for installed hooks.

When changing runtime behavior:

- Preserve empty-stdin success for hook commands.
- Preserve invalid JSON reporting to stderr with nonzero exit.
- Preserve daemon fallback semantics: accepted daemon failures should surface stderr/exit code; unavailable daemon should fall back to engine evaluation.
- Keep proxy fallback behavior intact when node/socket is unavailable.
- Add tests for direct CLI path, daemon path, parser registration, and installer proxy generation when applicable.

When enabling hooks/rules:

- Ensure the rule is included in the correct builder, such as `build_always_on_rules()` or `build_repo_strict_rules()`.
- Confirm enforcement mode: outside repo, repo strict, or repo relaxed.
- Respect `disabled_rules`, `severity_overrides`, skip paths, and repo enrollment.
- If adding config keys, update config coercion/loading, default policy, docs, and public contract tests.

## Testing strategy

Use targeted tests that match the changed surface:

- Rule behavior:
  - `tests/test_*rule*.py`
  - `tests/ast_rules/`
  - `tests/pytest_asyncio_rule/`
  - `tests/test_hypothesis_lint_rule_contracts/`
- Engine/public contracts:
  - `tests/engine/`
  - `tests/integration/test_guard_rule_public_api.py`
  - `tests/integration/test_python_ast_rule_public_api.py`
  - `tests/test_rule_and_config_public_contracts.py`
- Hook runtime/daemon:
  - `tests/integration/test_cli_hook_runtime.py`
  - `tests/integration/test_daemon_hook_integration.py`
  - `tests/test_daemon_hook.py`
- Installer/platform hooks:
  - `tests/test_installer_claude_hooks.py`
  - `tests/test_installer_cursor_hooks.py`
  - platform adapter tests near existing adapter coverage.
- Stateful hook behavior:
  - `tests/hook_state_spec/`
  - `tests/test_hook_state_spec.py`
- Size/module guard behavior:
  - `tests/size_guard_hook_behavior/`
  - `tests/test_size_guard_hook_behavior.py`

Prefer this validation ladder:

1. Narrow pytest selection for the touched rule/adapter/runtime behavior.
2. Related integration/public-contract tests.
3. `uv run pytest` for broad validation when the change affects public rule, adapter, config, or hook behavior.
4. Type/lint checks when function signatures, dataclasses, config schemas, or imports change:
   - `uv run basedpyright src tests`
   - `uv run ruff check src tests`

Use the repository's existing `pytest` configuration (`pythonpath = ["src"]`). If `uv` is unavailable, use the project's virtual environment or explain that validation could not be run.

## False-positive control

Every detector change should include both positive and negative tests.

For pattern rules:

- Include a minimal positive fixture that proves the intended violation fires.
- Include realistic allowed examples that are syntactically similar.
- Test event/tool mismatch returns no findings.
- Test path exclusions or config disablement if supported.
- Test metadata fields that make dashboard/debug output stable.

Avoid broad regex-only matching when AST/context can prevent false positives. If regex is appropriate, constrain by event, tool, target, path globs, and case/multiline settings.

## Documentation and compatibility

Update documentation when externally visible behavior changes:

- New rule IDs, decisions, severity, or remediation guidance.
- New or changed `slopgate.toml` keys.
- New hook installation behavior or daemon behavior.
- Platform capability changes.
- CLI command or argument changes.

Keep wording conservative:

- Say `partial`, `best-effort`, or `advisory` for limited platforms.
- Do not imply that Codex/OpenCode/Cursor can block every event Claude can block.
- Keep `README.md` claims aligned with `platform_capability()` and adapter behavior.

## Requirements gathering

When the user asks to create, update, or tune a rule/hook, first gather enough requirements to avoid encoding the wrong policy. Prefer answering these from the repo and the user's prompt; ask only for missing decisions that materially affect behavior.

Use this brief intake checklist:

1. **Intent**: What behavior should Slopgate prevent, steer, or observe?
2. **Trigger surface**: Which event(s), tools, payload fields, file paths, command text, prompts, outputs, or session state expose the signal?
3. **Action**: Should the response hard-block, ask, allow with mutation, add context, record trace metadata, or run post-edit validation?
4. **Scope**: Is this always-on, repo-strict only, language-specific, platform-specific, path-scoped, or opt-in through config?
5. **False positives**: Name at least two examples that must not fire.
6. **Remediation**: What should the agent/user do instead when the rule fires?
7. **Config**: Does the rule need thresholds, allowlists, disabled-rule support, severity overrides, or `slopgate.toml` fields?
8. **Platform compatibility**: Which harnesses must enforce it, and which can only provide advisory/context behavior?
9. **Testing**: What fixtures prove positive, negative, config-disabled, and platform-rendered behavior?
10. **Rollout**: Should this be enabled by default, guarded behind config, or documented as experimental?

If the user asks for a vague rule such as "catch bad tests" or "block unsafe commands", produce a one-paragraph requirements summary and ask for the missing policy boundary before implementation unless existing project docs already define it.

## Common implementation examples

### Example: small Python rule

Use this pattern for code-backed rules where regex config is too broad.

```python
from __future__ import annotations

from slopgate.constants import DENY, PRE_TOOL_USE
from slopgate.context import HookContext
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule


class NoSleepInTestsRule(Rule):
    rule_id = "PY-TEST-999"
    title = "Block time.sleep in tests"
    events = (PRE_TOOL_USE,)

    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for target in ctx.content_targets:
            if not target.path.endswith(".py") or "/test" not in target.path:
                continue
            if "time.sleep(" not in target.content:
                continue
            findings.append(
                RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.HIGH,
                    decision=DENY,
                    message=f"time.sleep() is blocked in test code: {target.path}",
                    additional_context="Use a fake clock, monkeypatch, or explicit synchronization instead of sleeping.",
                    metadata={"path": target.path, "source": target.source},
                )
            )
        return findings
```

Registration and tests are part of the change:

- Export/register the rule in `src/slopgate/rules/__init__.py` through the appropriate builder.
- Add direct rule tests with a constructed `HookContext`.
- Add engine/render tests if the rule's decision or event behavior is externally visible.

### Example: declarative regex rule

Prefer declarative regex for simple text/command/path policies that do not need AST or state.

```json
{
  "rule_id": "CUSTOM-001",
  "title": "Block TODO markers in Python",
  "severity": "HIGH",
  "events": ["PreToolUse", "PermissionRequest"],
  "target": "content",
  "path_globs": ["**/*.py"],
  "exclude_path_globs": ["docs/**"],
  "tool_matchers": ["Write", "Edit", "MultiEdit"],
  "patterns": ["#\\s*(TODO|FIXME|HACK|XXX)\\b"],
  "action": "deny",
  "message": "TODO/FIXME/HACK/XXX comments are blocked in {path}.",
  "additional_context": "Resolve the task or create an explicit tracked issue instead of leaving TODO comments."
}
```

Regex rule schema fields are documented in `docs/extension_guide.md`. Keep permanent built-in policies in bundled/default config only when the project intentionally ships them as defaults.

### Example: adapter output test shape

When adapter rendering changes, assert both the canonical event and the native output shape.

```python
from slopgate.adapters.claude import ClaudeAdapter
from slopgate.constants import DENY, PRE_TOOL_USE
from slopgate.models import RuleFinding, Severity


def test_claude_pre_tool_use_denial_output() -> None:
    finding = RuleFinding(
        rule_id="TEST-001",
        title="Test rule",
        severity=Severity.HIGH,
        decision=DENY,
        message="Denied for test coverage.",
    )

    output = ClaudeAdapter().render_output(
        PRE_TOOL_USE,
        [finding],
        context=None,
        updated_input={},
        decision=DENY,
    )

    assert output == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "[TEST-001 | HIGH] Denied for test coverage.",
        }
    }
```

Prefer testing through `evaluate_payload()` as well when a change depends on adapter normalization, decision ordering, enrichment, or tracing.

### Example: replay fixture

Use replay fixtures to validate realistic payloads captured from traces or hand-authored from harness schemas.

```bash
uv run slopgate replay --payload tests/fixtures/my_payload.json --platform claude --pretty
uv run slopgate replay --payload tests/fixtures/my_payload.json --platform opencode --pretty
```

Replay is especially useful for platform compatibility work because it exercises adapter normalization, engine evaluation, rendering, and trace output together.

## Harness schemas and contract resources

Use these repo resources before changing platform behavior:

| Resource | Use |
|---|---|
| `tests/fixtures/harness_schema_context.json` | Cross-checked harness event surfaces, installed-vs-official event lists, source IDs, and schema-context excerpts. Treat this as the local compatibility map, not as a substitute for current upstream docs. |
| `src/slopgate/adapters/base.py` | Shared render contract, `PlatformAdapter`, `RenderRequest`, and helper response builders. |
| `src/slopgate/adapters/claude.py` | Claude canonical event aliases and response rendering. |
| `src/slopgate/adapters/codex.py` | Codex normalization/rendering and partial hook assumptions. |
| `src/slopgate/adapters/opencode.py` | OpenCode plugin event mapping and action/context response rendering. |
| `src/slopgate/adapters/cursor.py` and `src/slopgate/adapters/cursor_output.py` | Cursor normalization and output constraints. |
| `src/slopgate/installer/_claude.py` | Slopgate's installed Claude event subset and settings merge behavior. |
| `src/slopgate/installer/hook_proxy.py` | Daemon proxy shell/node fallback contract for installed hooks. |
| `docs/architecture.md` | Pipeline overview, decision ordering, config discovery, trace/replay model. |
| `docs/extension_guide.md` | Regex rule schema, Python rule recipe, event-choice guidance, repo overrides. |
| `docs/rules_reference.md` | Existing rule inventory and enrichment expectations. |
| `docs/hook-state-test-matrix.md` | Stateful hook behavior coverage and scenarios. |
| `tests/integration/test_cli_hook_runtime.py` | CLI/daemon runtime contract examples. |
| `tests/test_installer_claude_hooks.py` and `tests/test_installer_cursor_hooks.py` | Installer/harness wiring expectations. |

When the local fixture and upstream docs disagree, prefer upstream docs for current platform semantics, then update `tests/fixtures/harness_schema_context.json`, adapter tests, installer tests, and documentation together.

## Harness schema quick reference

Slopgate rules should depend on the canonical payload shape after adapter normalization, not raw harness JSON unless the adapter itself is being changed.

Canonical input fields that rules commonly use:

| Field | Meaning |
|---|---|
| `hook_event_name` | Canonical Slopgate event such as `PreToolUse`, `PermissionRequest`, `PostToolUse`, `UserPromptSubmit`, `SessionStart`, or `Stop`. |
| `session_id` | Stable session/conversation ID when the harness supplies one. |
| `cwd` | Workspace/current directory used for repo discovery and trace context. |
| `tool_name` | Canonical tool name such as `Bash`, `Read`, `Write`, `Edit`, `MultiEdit`, `Grep`, `Glob`, `WebFetch`, or `WebSearch`. |
| `tool_input` | Tool arguments after adapter normalization; common keys include `command`, `file_path`, `content`, `edits`, `path`, `pattern`, and `url`. |
| `tool_response`, `tool_result`, `tool_output` | Post-tool result fields synchronized by adapters where available. |
| `prompt` | User prompt text for prompt-submission events. |
| `stop_response` | Final assistant response text for stop-like checks when available. |
| `model`, `provider` | Optional model/provider context for trace drilldowns. |
| `cursor_hook_event` / `opencode_hook_event` | Original native event name retained for diagnostics after Cursor/OpenCode normalization. |

Canonical output comes from `RuleFinding`, then adapters render platform-native JSON:

| Platform | Strong blocking shape | Advisory/context shape | Notes |
|---|---|---|---|
| Claude | `hookSpecificOutput.permissionDecision`, `decision: block`, or permission `decision.behavior` depending on event | `additionalContext` inside `hookSpecificOutput` or `systemMessage` | Reference/fullest hook surface; Slopgate installs a deliberate subset. |
| Codex | Claude-like `hookSpecificOutput` for pre/permission events; `decision: block`; critical post-tool may render `continue: false` | `hookSpecificOutput.additionalContext` or `systemMessage` | Partial/experimental; re-check current docs before adding claims. |
| OpenCode | `{action: "block", reason}` or `{action: "continue", reason}` for stop-like continuation | `{action: "context", context}` | Plugin-mediated; `tool.execute.before` is the strongest blocking point. |
| Cursor | Permission events render `permission: deny/ask/allow`; prompt submit renders `continue: false` | `agent_message`, `additional_context`, `followup_message`, or `user_message` depending on event | Several post-tool/after-edit paths are advisory/context-only. |

Minimal native-event mapping to remember:

| Platform | Native event examples | Canonical event |
|---|---|---|
| Claude | `PreToolUse`, `PermissionRequest`, `PostToolUse`, `UserPromptSubmit`, `Stop` | Same names after alias cleanup. |
| Codex | `pretooluse`, `permissionrequest`, `posttooluse`, `userpromptsubmit`, `stop` aliases | `PreToolUse`, `PermissionRequest`, `PostToolUse`, `UserPromptSubmit`, `Stop`. |
| OpenCode | `tool.execute.before`, `permission.asked`, `tool.execute.after`, `session.created`, `session.idle`, `file.edited` | `PreToolUse`, `PermissionRequest`, `PostToolUse`, `SessionStart`, `Stop`, `PostToolUse`. |
| Cursor | `preToolUse`, `beforeShellExecution`, `beforeSubmitPrompt`, `afterFileEdit`, `stop`, `subagentStop` | `PreToolUse`, `PreToolUse`, `UserPromptSubmit`, `PostToolUse`, `Stop`, `SubagentStop`. |

When adding a schema-dependent test, prefer a fixture that includes both the native event field and the expected canonical fields after normalization.

## Upstream harness documentation referral

Before making or reviewing platform claims, consult the current upstream harness docs. The local fixture records source IDs such as `claude_hooks`, `claude_settings`, `codex_hooks`, `codex_config_reference`, `opencode_plugin_docs`, and `opencode_config_schema`; use those IDs to connect fixture evidence to source documentation.

Recommended starting points:

- Claude Code hooks: <https://docs.anthropic.com/en/docs/claude-code/hooks>
- Claude Code settings: <https://docs.anthropic.com/en/docs/claude-code/settings>
- OpenCode plugin docs: <https://opencode.ai/docs/plugins/>
- OpenCode config docs/schema: <https://opencode.ai/docs/config/>
- Cursor agent hooks: <https://cursor.com/docs/agent/hooks>
- Codex CLI repository/docs: <https://github.com/openai/codex>

If a platform has changed since the local fixture was generated, update Slopgate conservatively:

1. Add or update a fixture entry showing the current upstream source and event/response schema.
2. Update adapter normalization/rendering.
3. Update installer wiring if the installed hook list changes.
4. Add contract tests proving the new behavior.
5. Update docs with capability wording such as `full`, `partial`, `degraded`, `best-effort`, or `advisory`.

## Completion criteria

A Slopgate rule/hook maintenance task is complete only when the touched surface satisfies these criteria.

For a new or changed rule:

- Requirements are explicit: trigger, scope, action, false-positive boundary, and remediation are clear.
- The rule is registered in the correct builder and respects enforcement mode.
- Rule IDs are stable, unique, and documented if public.
- Findings include actionable `message`, useful `additional_context` when needed, and stable JSON metadata.
- Positive, negative, event-mismatch, config-disabled, and path/tool-scope tests exist where relevant.
- Severity overrides and disabled rules still work.

For hook runtime or daemon changes:

- Empty stdin, invalid JSON, daemon handoff, daemon fallback, accepted daemon failure, and stdout/stderr/exit-code behavior remain covered.
- Parser arguments have validation tests.
- Proxy fallback still runs the original hook command when daemon/node/socket handling is unavailable.

For adapter/harness changes:

- Native event names normalize to canonical event names.
- Tool names, cwd/session fields, tool input, and tool output are preserved or intentionally transformed.
- Rendered output matches the current upstream schema and local adapter contract.
- Platform limitations are documented; no unsupported hard-blocking claims are introduced.
- `tests/fixtures/harness_schema_context.json` is updated if the harness schema changed.

For docs/config changes:

- `docs/extension_guide.md`, `docs/rules_reference.md`, `docs/architecture.md`, or README are updated when public behavior changes.
- New config keys have defaults, coercion/loading behavior, and public contract tests.
- Rollout state is clear: default-on, repo-strict, opt-in, experimental, or advisory-only.

## Final review checklist

Before finishing a Slopgate rule/hook maintenance task, confirm:

- The change is in maintainer code, not `bundle/`, unless the user explicitly asked for distribution assets.
- Requirements and completion criteria are satisfied for the touched surface.
- The rule or hook uses canonical event names and constants.
- Platform-specific behavior lives in adapters/installers, not rule bodies.
- New findings have stable IDs, messages, metadata, severity, and decision semantics.
- Harness schema assumptions were checked against `tests/fixtures/harness_schema_context.json` and current upstream docs when platform behavior changed.
- Tests cover positive, negative, config/disablement, and platform response behavior where relevant.
- Hook runtime changes preserve daemon fallback and CLI stdin/error semantics.
- Docs are updated for public behavior changes.
- Validation commands and results are reported clearly.
