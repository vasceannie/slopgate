## Conclusion

I would **not** make OMP an alias for the existing Pi adapter. They share ancestry, but OMP has already diverged in exactly the places Slopgate cares about most: stop semantics, tool-result interception, extension loading, and some event payload contracts. The safest design is a **first-class `omp` platform built on shared Pi-family normalization helpers**, plus contract tests that execute OMP's actual `ExtensionRunner` at a pinned version.

That matters because the current Pi tests are mostly good unit/template tests, but they are not host-contract tests. `tests/test_pi_extension_template.py:16-25` literally validates source substrings, while `tests/adapters/test_13_pi_adapter_contract.py:8-31` feeds hand-built dictionaries directly into `PiAdapter`. Useful? Certainly. Proof that OMP will actually honor the adapter? Not remotely. Humans have invented more sophisticated ways of testing their assumptions, apparently.

I did try the requested LiteLLM/GitNexus path repeatedly, but its MCP endpoint is currently returning `ConnectError: All connection attempts failed`. I therefore inspected the repository through the connected GitHub source at commit `4bd086a0971a7e7dbbde1d63be3cc06fb6670cc7` and checked current OMP docs/runtime tests separately. Anything needing GitNexus call-graph proof is marked **Unverified**.

## Findings

| Severity     | Type                       | Finding                                                                              | Evidence                                                                                                                                                                                                          | Why it matters                                                                                                                                                                                         | Recommended fix                                                                                                                                                                                                      |
| ------------ | -------------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | **documentation mismatch** | Pi's concept of `Stop` is wrong for current OMP                                      | `src/slopgate/adapters/pi.py:59-67` maps `agent_end -> Stop`; `src/slopgate/resources/pi_extension.ts:72-81` has no `session_stop`; `src/slopgate/adapters/pi.py:166-176` only blocks pre-tool/user-prompt events | OMP documents `agent_end` as notification-only. Its actual loop-control surface is `session_stop`, which can request another pass. ([GitHub][1])                                                       | Add `OmpAdapter`; map `session_stop -> Stop`; treat `agent_end` as telemetry. Give OMP a Stop-specific renderer.                                                                                                     |
| **High**     | **confirmed behavior**     | Slopgate has no OMP platform or OMP-native install site                              | `src/slopgate/cli/platforms.py:7-9`; `src/slopgate/adapters/__init__.py:31-37`; `src/slopgate/installer/_pi.py:72-94`; `src/slopgate/installer/_suite.py:88-116`                                                  | OMP natively discovers `<cwd>/.omp/extensions` and `~/.omp/agent/extensions`; `.pi/extensions` is not its native auto-discovery root. ([GitHub][2])                                                    | Add `_omp.py`, `.omp` paths, `"omp"` platform registration, suite discovery, profile/custom-agent-dir support.                                                                                                       |
| **High**     | **documentation mismatch** | Current Pi bridge hand-defines the host contract and uses a legacy Pi UI namespace   | `src/slopgate/resources/pi_extension.ts:15-19`, `:72-112`, `:175-212`                                                                                                                                             | OMP says extensions should consume `ExtensionAPI` from `@oh-my-pi/pi-coding-agent`. Legacy compatibility has had recent concrete runtime breakages. ([GitHub][2])                                      | OMP extension should compile against OMP's official API, not copied local interfaces or `@earendil-works/*`.                                                                                                         |
| **High**     | **documentation mismatch** | Pi post-tool mapping is already internally inconsistent, and OMP further diverges    | `src/slopgate/adapters/pi.py:3-7` says failed `tool_execution_end -> PostToolUseFailure`, but `src/slopgate/adapters/pi.py:59-64` maps every `tool_execution_end -> PostToolUse`                                  | In OMP, `tool_result` is the authoritative mutable post-execution event; `tool_execution_end` is observability. Failures surface through `tool_result.isError`. ([GitHub][1])                          | OMP should enforce post-tool policy on `tool_result`; use `isError` to select PostToolUse vs PostToolUseFailure; keep execution-end telemetry-only.                                                                  |
| **High**     | **documentation mismatch** | Existing “documented” Pi tests mostly prove source shape, not runtime behavior       | `tests/test_pi_extension_template.py:16-25`, `:44-84`; `tests/adapters/test_13_pi_adapter_contract.py:8-31`, `:85-105`, `:122-151`                                                                                | A typo in our understanding of OMP can be faithfully encoded into tests and then blessed forever.                                                                                                      | Introduce pinned OMP runner tests and generate adapter fixtures from observed runtime events. Keep marker tests only as cheap template invariants.                                                                   |
| **Medium**   | **documentation mismatch** | Pi mutates tool input locally rather than proving the host's native replacement path | `src/slopgate/resources/pi_extension.ts:234-241`                                                                                                                                                                  | Current OMP's `tool_call` contract explicitly supports returning replacement `input`, which is then revalidated and propagated through scheduling, persistence, approval, and execution. ([GitHub][1]) | Return OMP-native `{ input: updatedInput }` and test that the underlying tool receives the changed arguments.                                                                                                        |
| **Medium**   | **intended escape hatch**  | The bridge already has a useful managed-repo sentinel mechanism                      | `src/slopgate/resources/pi_extension.ts:216-228` walks parents for `slopgate.toml`                                                                                                                                | That boundary is worth retaining so a user-installed extension does not turn ordinary shell/sysadmin work into Slopgate's private police state.                                                        | Extract scope classification into shared bridge logic and contract-test managed repo vs ordinary workstation/server directories. Full downstream enforcement behavior is **Unverified** until GitNexus is reachable. |

## 1. Make OMP a sibling of Pi, not an alias

The clean model is:

```text
                 shared Pi-family translation
                          │
               ┌──────────┴──────────┐
               │                     │
          PiAdapter              OmpAdapter
          Pi bridge              OMP bridge
          .pi loader             .omp loader
          Pi semantics           OMP semantics
```

Share things that are actually common: tool-name normalization, canonical payload field helpers, shell-command extraction, session identifiers, subprocess invocation, and perhaps message formatting.

Keep **event maps and host return values separate**. The first implementation should roughly treat the OMP lifecycle as:

| OMP event                      | Slopgate interpretation |
| ------------------------------ | ----------------------- |
| `tool_call`                    | `PreToolUse`            |
| `tool_result`, `isError=false` | `PostToolUse`           |
| `tool_result`, `isError=true`  | `PostToolUseFailure`    |
| `session_start`                | `SessionStart`          |
| `input`                        | `UserPromptSubmit`      |
| `turn_end`                     | `TurnEnd`               |
| `session_stop`                 | `Stop`                  |
| `agent_end`                    | notification/telemetry  |
| `tool_execution_end`           | notification/telemetry  |

This is materially different from `src/slopgate/adapters/pi.py:59-67`, where `agent_end` is the canonical Stop and `tool_execution_end` is treated as PostToolUse.

OMP explicitly documents `session_stop` as the **main-session stop hook**, executed before settling. It can return either continuation feedback or a blocking decision, has an eight-continuation cap, and doesn't run for task/subagent sessions. OMP's own runtime tests verify that continuation causes a second model invocation and that repeated blocks are capped. ([GitHub][1])

That leads to another important change: merely adding this alias would be insufficient:

```python
"session_stop": STOP
```

`PiAdapter.render_output()` currently permits blocking only when the canonical event is `PreToolUse` or `UserPromptSubmit`, at `src/slopgate/adapters/pi.py:160-176`. So `OmpAdapter.render_output()` needs explicit Stop behavior.

For repair-oriented Slopgate findings, I would preferentially render something semantically equivalent to:

```ts
{
  continue: true,
  additionalContext: "Slopgate found ... Fix these before finishing."
}
```

rather than pretending a normal `agent_end` callback can keep the model working. OMP's own tests prove the continuation reaches the next model pass. ([GitHub][3])

One thing I would leave **Unverified** until GitNexus works again is whether Slopgate's current consumers truly want `before_agent_start -> SessionStart`. That's today's mapping at `src/slopgate/adapters/pi.py:63-67`, but OMP has an actual `session_start` event and treats `before_agent_start` as per-turn injection. I would trace every `SessionStart` rule before preserving that historical conflation.

## 2. Build an OMP-native extension

I would create `src/slopgate/resources/omp_extension.ts` rather than parameterizing today's Pi template immediately.

Its contract starts with OMP itself:

```ts
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

export default function slopgateOmpExtension(pi: ExtensionAPI) {
  // registrations only here
}
```

That's the contract in OMP's current authoring material. Factories register during loading, and live actions are wired only after `ExtensionRunner.initialize()`. Calling runtime actions during extension initialization is deliberately rejected. ([GitHub][2])

This also means I would **not** copy the hand-maintained `PiExtensionAPI`/`PiEventLike` definitions from `src/slopgate/resources/pi_extension.ts:72-112` and `:175-212`. Let TypeScript break when OMP changes the contract. That's considerably more useful than Slopgate maintaining an exquisitely typed description of what we hope OMP does.

The legacy compatibility layer is especially unsuitable as your contract boundary. OMP still accepts Pi manifests/import compatibility, but it has had recent failures resolving `@earendil-works/*`, and an August 2026 report specifically shows OMP's `before_agent_start` payload diverging from the Pi contract despite the legacy import rewrite. ([GitHub][4])

### Installer shape

Add `src/slopgate/installer/_omp.py`. Unlike `_pi.py`, whose paths are explicitly `.pi` at `src/slopgate/installer/_pi.py:72-94`, the OMP installer should understand:

```text
project: <repo>/.omp/extensions/slopgate/index.ts
user:    ~/.omp/agent/extensions/slopgate/index.ts
profile: ~/.omp/profiles/<profile>/agent/extensions/slopgate/index.ts
```

It should also honor OMP's active agent directory behavior, including `PI_CODING_AGENT_DIR`. OMP's project auto-discovery is **cwd-only**, not ancestor-walking. ([GitHub][5])

That last bit is useful: OMP doesn't need to walk ancestors to *load* the project extension, but a **user-installed Slopgate extension can still walk ancestors for `slopgate.toml` to decide enforcement scope**. Those are separate concerns and shouldn't be mashed together.

For an installable package, prefer the native manifest:

```json
{
  "omp": {
    "extensions": ["./index.ts"]
  }
}
```

OMP accepts `pi.extensions` for compatibility, but there is no upside to choosing the compatibility spelling for new Slopgate code. ([GitHub][2])

Registration also needs to extend `VALID_PLATFORMS` at `src/slopgate/cli/platforms.py:7-9`, `ADAPTERS` at `src/slopgate/adapters/__init__.py:31-37`, and suite discovery currently ending in Pi at `src/slopgate/installer/_suite.py:88-116`.

## 3. Make runtime the test oracle

I would use six layers, with only the first few running on every PR:

1. **Pinned compile contract, PR-blocking.** Put an exact `@oh-my-pi/pi-coding-agent` version in a test-only Bun workspace. No caret. Compile `omp_extension.ts` against its actual exported `ExtensionAPI`. Unsupported event names or return shapes then fail at compile time.

2. **Real `ExtensionRunner` contract tests, PR-blocking.** OMP itself imports `ExtensionRuntime`, `loadExtensionFromFactory`, and `ExtensionRunner` from public package subpaths in its tests, while using mock models rather than calling Anthropic/OpenAI. Copy that testing *architecture*, not its expected values. ([GitHub][3]) Test real `tool_call` block/allow, input replacement, success/failure `tool_result`, `session_stop`, `before_agent_start`, and `agent_end`.

3. **Runtime-captured Python adapter fixtures.** The TypeScript harness should record what OMP actually emitted, for example `tests/fixtures/omp/<version>/tool-call-bash.json`. Feed those captured payloads into `OmpAdapter.normalize_payload()`. Never invent the event dictionary twice, once in TS and once in Python, because then the two inventions merely agree with each other.

4. **Installer + real loader test.** Create fake `$HOME`, project, profile and custom agent-root directories; call `_omp.py`; then invoke OMP's actual discovery/loading path and assert the extension is found once with zero load errors. `Path.exists()` is not sufficient. OMP's loader has source-specific discovery and de-duplication rules. ([GitHub][5])

5. **Pinned end-to-end semantic tests.** Most important assertions should ask what happened, not what object happened to look like. For tool mutation, verify the underlying mock tool receives the rewritten arguments. For `session_stop`, verify another mock-model pass actually occurs and receives the Slopgate guidance. OMP already uses this style in its own session-stop tests. ([GitHub][3])

6. **Latest-OMP drift lane, non-blocking until reviewed.** Keep PR tests pinned. Separately run the same contract suite against current/latest OMP on a schedule. A failure signals a host-contract change. Do **not** automatically regenerate fixtures to make it green. That would be CI laundering.

The resulting test surface would look roughly like:

```text
tests/adapters/test_omp_adapter_contract.py
tests/test_installer_omp_extension.py
tests/test_omp_extension_source_contract.py     # small static invariants only

tests/runtime/omp/
  package.json                                  # exact OMP dependency
  bun.lock
  extension-contract.test.ts
  discovery-contract.test.ts
  capture-contract.ts

tests/fixtures/omp/
  <pinned-version>/
    tool-call-write.json
    tool-call-bash.json
    tool-result-success.json
    tool-result-error.json
    session-start.json
    before-agent-start.json
    session-stop.json
```

I'd also rename or conceptually downgrade tests like `tests/test_pi_extension_template.py:44-84` from “documented contract” tests to **source invariants**. They are perfectly legitimate checks, just not evidence that the host runtime behaves that way.

### Minimum acceptance matrix

The OMP adapter should not be considered complete until the pinned host harness proves these outcomes:

| Scenario                              | Required observation                                        |
| ------------------------------------- | ----------------------------------------------------------- |
| blocked write                         | underlying tool never executes                              |
| allowed write                         | executes exactly once                                       |
| rewritten input                       | executed args equal Slopgate's rewrite                      |
| failed tool                           | adapter receives canonical `PostToolUseFailure`             |
| post-tool patch                       | patched result reaches provider/session context as intended |
| clean `session_stop`                  | session settles normally                                    |
| violating `session_stop`              | another agent pass occurs with repair guidance              |
| `agent_end` finding                   | cannot masquerade as Stop enforcement                       |
| extension outside managed repo        | repo-only policy doesn't block                              |
| enforcer failure inside managed repo  | configured fail-closed behavior occurs                      |
| enforcer failure outside managed repo | no repo-quality global blockade                             |
| OMP version bump                      | pinned fixtures remain immutable until reviewed             |

OMP's own documentation says a `tool_call` replacement input is propagated through revalidation, scheduling, persisted assistant state, approval, and execution. Your runtime test should validate at least execution and one upstream representation rather than merely checking the handler returned `{input: ...}`. ([GitHub][1])

## 4. One existing bug I'd correct while extracting shared behavior

The Pi adapter's comment/documentation says:

```text
tool_execution_end (non-zero) -> PostToolUseFailure
```

at `src/slopgate/adapters/pi.py:3-7`.

But the actual aliases contain:

```python
"tool_execution_end": POST_TOOL_USE
```

at `src/slopgate/adapters/pi.py:59-64`.

So that is a **confirmed documentation mismatch**, independent of OMP. I would not use the current Pi implementation as the golden template until that discrepancy has a runtime-backed resolution.

For OMP the resolution is simpler: don't use `tool_execution_end` for enforcement at all. Its current docs call `tool_execution_start/update/end` **observability events**, while `tool_result` is the mutable post-execution contract and carries `isError`. ([GitHub][1])

## Policy Boundary Recommendations

The OMP work is also a good place to formalize the distinction between “globally installed” and “globally enforced.” Those are not the same thing, despite software's recurring desire to make configuration nouns mean four different things.

| Environment                 | Recommended mode                                                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **project repo work**       | Full blocking Slopgate policy after managed-repo classification                                                                      |
| **general workstation use** | Repo-oriented rules inactive; at most narrowly defined global safety checks                                                          |
| **server operations**       | Repo-oriented rules inactive outside an explicitly managed repo; shell/system-path administration must not inherit coding guardrails |

The parent sentinel mechanism already exists in `findManagedRepoRoot()` at `src/slopgate/resources/pi_extension.ts:216-228`. Preserve that concept in shared Pi/OMP bridge code, but make the resulting policy mode explicit instead of scattering `if (managedRepo)` checks throughout an extension.

I would model it as something like:

```text
unmanaged
  -> global-safety rules only
  -> repo quality / post-edit / stop / anti-bypass rules inactive

managed repo
  -> global-safety
  -> repo coding rules
  -> post-edit quality
  -> stop/completion enforcement
  -> config/extension anti-bypass
```

And put the same destructive-looking command through three runtime tests: once inside a temp repo containing `slopgate.toml`, once in an ordinary temp/workstation directory, and once in a fake server-admin context such as `/etc` or an equivalent isolated path. The repo-only rule must fire only in the first case.

The narrowest safe implementation is therefore: **add `omp` as a distinct platform, extract only genuinely shared Pi-family translation helpers, install an OMP-native extension into `.omp`, pin OMP's coding-agent runtime in a Bun contract harness, and generate Python adapter fixtures from that runner rather than from documentation examples.** That gives you tests that fail when either the docs or the runtime changes, which is considerably more useful than choosing one authority and discovering six months later that the other one wandered off.

[1]: https://github.com/can1357/oh-my-pi/blob/main/docs/extensions.md?utm_source=chatgpt.com "oh-my-pi/docs/extensions.md at main · can1357/oh-my-pi · GitHub"
[2]: https://github.com/can1357/oh-my-pi/blob/main/docs/skills/authoring-extensions.md?utm_source=chatgpt.com "oh-my-pi/docs/skills/authoring-extensions.md at main · can1357/oh-my-pi · GitHub"
[3]: https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/test/agent-session-concurrent.test.ts?utm_source=chatgpt.com "oh-my-pi/packages/coding-agent/test/agent-session-concurrent.test.ts at main · can1357/oh-my-pi · GitHub"
[4]: https://github.com/can1357/oh-my-pi/issues/6173?utm_source=chatgpt.com "v17: @earendil-works/* peer dep resolution still broken for community plugins (pi-web-access, pi-vimmode) · Issue #6173 · can1357/oh-my-pi · GitHub"
[5]: https://github.com/can1357/oh-my-pi/blob/main/docs/extension-loading.md?utm_source=chatgpt.com "oh-my-pi/docs/extension-loading.md at main · can1357/oh-my-pi · GitHub"
