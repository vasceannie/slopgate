## Conclusion

Treat **OMP as a Pi-family host, not as “Pi with a different executable.”** The canonical event mapping is reusable, but OMP has diverged in discovery paths, result shapes, stop semantics, and newer events. Slopgate’s adapter registry is already structured well enough to support a separate `OmpAdapter`, so I would share normalization logic with `PiAdapter` while giving OMP its own TypeScript bridge and installer. `src/slopgate/adapters/__init__.py:31-55`

There are already concrete incompatibilities if the existing Pi bridge is used unchanged with current OMP. Most seriously, Slopgate returns `{ action: "handled" }` to block user input, while OMP only checks `handled: true`, meaning the supposedly blocked prompt continues. `src/slopgate/resources/pi_extension.ts:720-734`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/types.ts:1117-1125`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/runner.ts:1576-1600`

I did invoke GitNexus through the requested LiteLLM MCP, but that endpoint currently returns **“User not allowed to call this tool.”** I therefore used the repository connector as a read-only fallback for Slopgate and the current OMP source. Anything not established from those files below is marked `Unverified`, rather than engaging in the traditional software-engineering sport of confidently inventing facts.

### Findings


| Severity     | Type                   | Finding                                                                                                                                                                                    | Evidence                                                                                                                                                                                                                      | Why it matters                                                                                                                                                                                    | Recommended fix                                                                                                                            |
| ------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Critical** | documentation mismatch | OMP prompt blocking is currently expressed with the wrong result shape. Slopgate returns `{ action: "handled" }`; OMP requires `handled?: boolean` and explicitly checks `result.handled`. | `src/slopgate/resources/pi_extension.ts:720-734`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/types.ts:1117-1125`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/runner.ts:1576-1600`         | A `UserPromptSubmit` decision can appear blocked to Slopgate while OMP continues processing the prompt.                                                                                           | OMP bridge should return `{ handled: true }` for denial and `{ text: replacement }` for transforms. Remove the invented `action` protocol. |
| **High**     | documentation mismatch | Stop enforcement is wired to `agent_end`, not OMP's purpose-built `session_stop`. `agent_end` can explicitly occur while the agent will continue.                                          | `src/slopgate/adapters/pi.py:1-12,59-68`; `src/slopgate/resources/pi_extension.ts:745-757`; `oh-my-pi/packages/coding-agent/src/extensibility/shared-events.ts:96-107,192-202,393-403`                                        | Stop/post-quality rules can run at the wrong lifecycle point, and the current adapter cannot request the OMP continuation needed to correct a failed stop check.                                  | Map OMP `session_stop -> Stop`; use `{ continue: true, additionalContext: reason }`; honor `stop_hook_active` to prevent loops.            |
| **High**     | documentation mismatch | The Pi installer writes to `.pi` locations that OMP does **not** natively auto-discover.                                                                                                   | `src/slopgate/installer/_pi.py:72-90`; `oh-my-pi/docs/[extension-loading.md:28](http://extension-loading.md:28)-43`                                                                                                           | A perfectly written adapter is fairly ornamental if OMP never loads it.                                                                                                                           | Add `_[omp.py](http://omp.py)` using `<cwd>/.omp/extensions/` and the active OMP agent directory, default `~/.omp/agent/extensions/`.      |
| **High**     | accidental loophole    | Updated tool input is applied by mutating `event.input`, whereas OMP's supported contract is returning `ToolCallEventResult.input` as the raw replacement execution parameters.            | `src/slopgate/resources/pi_extension.ts:234-242,684-706`; `oh-my-pi/packages/coding-agent/src/extensibility/shared-events.ts:306-332`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/wrapper.ts:202-245`       | It may accidentally work for some tools but fail for normalized inputs, especially `edit`; worse, approval may not correspond to what Slopgate thought it rewrote.                                | Return `{ input: rawReplacement }`. Do not mutate `event.input`. Add tool-specific rewrite conversion and runtime-test it.                 |
| **High**     | documentation mismatch | OMP has a direct `user_python` execution event that the current Pi bridge doesn't subscribe to.                                                                                            | `src/slopgate/resources/pi_extension.ts:72-81,676-773`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/types.ts:885-893,1285-1292`                                                                              | Inside managed repos, `$`/`$$` Python execution is an execution path not covered by the existing direct-shell `user_bash` gate.                                                                   | Add OMP-native `user_python` handling, repo-scoped like direct shell execution.                                                            |
| **High**     | confirmed behavior     | Managed-repo detection affects degraded fail-closed behavior, but the enforcer is still spawned outside managed repos.                                                                     | `src/slopgate/resources/pi_extension.ts:216-228,593-674`                                                                                                                                                                      | Valid global enforcer responses can still affect ordinary workstation/server activity. Whether current downstream config actually blocks there is **Unverified** without engine/config discovery. | Explicitly distinguish `managed_repo` and `outside_repo`; initially no-op repo-only policies outside a managed repo.                       |
| **Medium**   | documentation mismatch | The bridge hand-maintains its own approximation of Pi's TypeScript API, and tests explicitly enforce those local declarations instead of upstream `ExtensionAPI`.                          | `src/slopgate/resources/pi_extension.ts:72-214`; `tests/test_pi_extension_template.py:181-208`; `oh-my-pi/docs/skills/[authoring-extensions.md:10](http://authoring-extensions.md:10)-35`                                     | Upstream can change while Slopgate continues compiling against its own fiction. That has already happened with input results.                                                                     | OMP bridge should `import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent"`. Compile it against a pinned real OMP package.           |
| **Medium**   | intended escape hatch  | Slopgate types `before_agent_start.systemPrompt` as a string; current OMP types it as `string[]`, although its runtime intentionally wraps legacy strings.                                 | `src/slopgate/resources/pi_extension.ts:348-375`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/types.ts:755-761,1141-1145`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/runner.ts:1700-1747` | It works today only because OMP carries compatibility logic.                                                                                                                                      | OMP adapter should use the current `string[]` contract rather than depending on legacy coercion.                                           |
| **Low**      | confirmed behavior     | Most useful Pi-style event names still exist in OMP, including `before_agent_start`, `tool_call`, `tool_result`, `input`, `turn_end`, and `user_bash`.                                     | `oh-my-pi/packages/coding-agent/src/extensibility/extensions/types.ts:1236-1292`                                                                                                                                              | You do **not** need to duplicate all canonical normalization logic merely because the host is OMP.                                                                                                | Extract/share a Pi-family normalization core while keeping host-specific transport semantics separate.                                     |


## Detailed analysis

### 1. Split OMP transport from Pi normalization

I would make `OmpAdapter` a distinct registered platform rather than adding OMP branches throughout `PiAdapter`. Slopgate already dispatches adapters generically by platform name, so `"omp": OmpAdapter` is a natural extension rather than an architectural surgery performed with oven mitts. `src/slopgate/adapters/__init__.py:31-55`

The reusable part is canonicalization. OMP still exposes `tool_call`, `tool_result`, `before_agent_start`, `input`, `turn_end`, `agent_end`, and `user_bash`, so much of `PiAdapter.normalize_payload()` can live in something like `_pi_[family.py](http://family.py)`. `src/slopgate/adapters/pi.py:47-152`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/types.ts:1236-1292`

The **non-reusable** part should be the host boundary: output/result shapes, lifecycle semantics, installation paths, host-specific events, and TypeScript API types. Those have already diverged enough to justify the separation. `oh-my-pi/docs/skills/[authoring-extensions.md:76](http://authoring-extensions.md:76)-99,196-231`

A sensible file boundary would therefore be:

```text
src/slopgate/adapters/_pi_family.py
src/slopgate/adapters/pi.py
src/slopgate/adapters/omp.py

src/slopgate/resources/pi_extension.ts
src/slopgate/resources/omp_extension.ts

src/slopgate/installer/_pi.py
src/slopgate/installer/_omp.py
```

The OMP extension should call `slopgate handle --platform omp`, instead of masquerading as Pi all the way through the engine. The current bridge hardcodes `--platform pi`. `src/slopgate/resources/pi_extension.ts:593-605`

### 2. Fix the lifecycle semantics before expanding coverage

The input result is the clearest bug. Slopgate's local type invented `action: "transform"` / `action: "handled"` semantics, and its source tests dutifully verify those strings. `src/slopgate/resources/pi_extension.ts:146-159,334-346,720-734`; `tests/test_pi_extension_template.py:44-81`

OMP's actual contract has no `action` property. `InputEventResult` contains `handled`, `text`, and `images`, and `emitInput()` short-circuits only on `handled`. `oh-my-pi/packages/coding-agent/src/extensibility/extensions/types.ts:1117-1125`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/runner.ts:1576-1600`

So the OMP shapes should effectively be:

```ts
// deny
return { handled: true }

// rewrite
return { text: replacement }
```

Stop handling deserves the same treatment. OMP describes `session_stop` as the point where a main-agent turn is about to settle and lets extensions request another continuation turn. `oh-my-pi/packages/coding-agent/src/extensibility/shared-events.ts:96-107,393-403`

By contrast, `agent_end` merely means an agent loop ended, and its `willContinue` flag explicitly warns consumers not to treat every occurrence as a user-visible terminal settle. `oh-my-pi/packages/coding-agent/src/extensibility/shared-events.ts:192-202`

Current Slopgate maps `agent_end -> Stop`, has no `session_stop` alias, and `render_output()` only emits blocking results for `PreToolUse` and `UserPromptSubmit`. `src/slopgate/adapters/pi.py:59-68,155-186`

For OMP, I would instead map `session_stop -> Stop` and make a failed Stop rule produce an OMP continuation. OMP itself documents the pattern and exposes `stop_hook_active` specifically to prevent endless continuation loops. `oh-my-pi/docs/skills/[authoring-extensions.md:196](http://authoring-extensions.md:196)-217`

### 3. Do not implement tool rewriting by mutating OMP's event

Current Slopgate does this:

```ts
Object.assign(event.input, updatedInput)
```

`src/slopgate/resources/pi_extension.ts:234-242`

OMP's contract says something materially different. A `tool_call` handler may return an `input` object, and that object becomes the **raw execution parameters**. OMP then runs its approval gate against that revised input. `oh-my-pi/packages/coding-agent/src/extensibility/shared-events.ts:306-332`; `oh-my-pi/packages/coding-agent/src/extensibility/extensions/wrapper.ts:202-246`

This distinction matters because OMP's normalized event input can contain gate-only derived fields. Its `edit` normalizer, for example, derives `path`/`paths` from hashline patches specifically for policy interception without changing the real tool execution parameters. `oh-my-pi/packages/coding-agent/src/extensibility/tool-event-input.ts:58-79`

Therefore **do not simply return** `{ input: event.input }` **either**. For transformations, the OMP bridge needs to retain/reconstruct the raw tool parameter shape. Until that conversion is proven for a tool, I would prefer “allow/block only” over a speculative rewrite. Guardrails that silently rewrite the wrong object are impressively worse than guardrails that admit they cannot rewrite it.

### 4. Replace source-marker tests with an upstream-contract test pyramid

The existing tests are useful as internal unit tests, but they are not an OMP compatibility suite. `tests/adapters/test_13_pi_adapter_contract.py:8-150` validates Python normalization by feeding `PiAdapter` hand-authored dictionaries, while `tests/test_pi_extension_template.py:16-225` mostly searches the generated TypeScript source for expected strings.

Worse, the template test deliberately requires locally declared `PiExtensionAPI` types rather than importing the real coding-agent API. `tests/test_pi_extension_template.py:181-208`

For OMP, I would use four layers:

**Compile contract.** Render the actual `omp_extension.ts` and run `tsc --noEmit` against an exact `@oh-my-pi/pi-coding-agent` version. The current upstream package snapshot is `18.0.5`. `oh-my-pi/packages/coding-agent/package.json:4` The extension factory should take the real `ExtensionAPI`, exactly as OMP's authoring documentation shows. `oh-my-pi/docs/skills/[authoring-extensions.md:10](http://authoring-extensions.md:10)-35`

**Host-runner contract.** Execute the rendered extension through OMP's own extension runner rather than a Slopgate-written fake `pi.on()` implementation. The package exports the extension implementation subpaths needed for a test harness. `oh-my-pi/packages/coding-agent/package.json:306-312` This suite should prove that input denial actually short-circuits, text replacement actually propagates, `tool_call` block prevents execution, returned `input` replaces the actual execution parameters, and `session_stop` requests exactly one continuation.

**Discovery/install contract.** Give tests an isolated HOME/CWD and use OMP's actual discovery implementation to prove that Slopgate is loaded from `.omp`. Current OMP uses `<cwd>/.omp/extensions` and the active user's agent directory, and explicitly states that `.pi/extensions` is **not** a native extension root. `oh-my-pi/docs/[extension-loading.md:28](http://extension-loading.md:28)-43` Also test `PI_CODING_AGENT_DIR`/profile behavior because OMP's user root is profile-sensitive. `oh-my-pi/docs/skills/[authoring-extensions.md:76](http://authoring-extensions.md:76)-99`

**Black-box smoke.** Run a pinned real `omp` executable with the rendered extension and a fake deterministic `slopgate` executable that records stdin and returns controlled JSON. Validate extension load through OMP's structured logs, whose documented default is under `~/.omp/logs`. `oh-my-pi/docs/skills/[authoring-extensions.md:233](http://authoring-extensions.md:233)-251` The exact best noninteractive OMP invocation/provider fixture is **Unverified** until the corresponding OMP CLI/SDK test harness is inspected.

This establishes a much better authority chain:

**OMP types → OMP runtime → OMP docs → Slopgate assumptions.**

When OMP docs and runtime disagree, the runtime contract should control behavior and a separate conformance test should make the documentation discrepancy visible. Otherwise you eventually end up with a test called `test_documented_behavior` that faithfully verifies something no program has done for six releases. Humans are remarkably dedicated to this genre.

### 5. Add an upstream-version contract instead of silently following latest

Pin the OMP package used by required CI. Current inspected OMP is `@oh-my-pi/pi-coding-agent` `18.0.5`. `oh-my-pi/packages/coding-agent/package.json:4`

Then maintain a second update/conformance lane against a newer OMP version before changing that pin. This makes upstream drift an explicit dependency update instead of a random Tuesday breaking all Slopgate builds. The compile contract will immediately catch things such as the current `systemPrompt: string[]` signature that Slopgate's handwritten interface misses. `oh-my-pi/packages/coding-agent/src/extensibility/extensions/types.ts:755-761,1141-1145`

For every supported upstream version, I would record the OMP package version and upstream commit alongside the fixtures. Tests should carry **real OMP event payloads or instantiate OMP's own runner**, not manually reproduce what someone remembers the documentation saying.

## Policy Boundary Recommendations

The OMP integration should explicitly separate **transport availability** from **policy enforcement scope**. OMP's project-native extension discovery is CWD-only and does not walk ancestor directories. `oh-my-pi/docs/[extension-loading.md:34](http://extension-loading.md:34)-43` Meanwhile Slopgate already walks upward from `ctx.cwd` looking for `slopgate.toml`. `src/slopgate/resources/pi_extension.ts:216-228`

That means the most reliable installation model is arguably a **user-level OMP extension that can load everywhere**, combined with a strict Slopgate policy gate that activates repo-oriented rules only when `findManagedRepoRoot()` succeeds. This preserves enforcement when OMP is launched from `repo/src/foo`, without forcing every normal workstation or server shell operation through repo-quality rules. The current implementation already uses the managed-repo signal for protected-write and degraded-mode decisions, but still invokes the enforcer outside repositories. `src/slopgate/resources/pi_extension.ts:593-674,684-698`

For **project repo work**, OMP should enable strong tool blocking, prompt interception, direct Bash/Python gates, stop continuation, post-edit quality checks, and fail-closed behavior. For **general workstation use**, those repo coding controls should be inactive or advisory. For **server operations**, repo-oriented shell and protected-path checks should likewise remain inactive unless the target/current directory is explicitly managed; indiscriminately blocking system-path administration is precisely the sort of safety mechanism that eventually causes someone to disable the entire mechanism.

The narrowest immediate fix is to make the new OMP bridge **no-op for repo-specific enforcement when no managed** `slopgate.toml` **ancestor exists**. Then, separately, introduce an explicit engine-level scope such as `managed_repo` versus `global`, with a deliberately small `global_safety` rule tier. Whether Slopgate already has sufficient downstream configuration primitives to implement that tier cleanly is **Unverified** because GitNexus access to the engine/config graph was denied.

So the implementation order I would use is: **add** `OmpAdapter` **→ add typed** `omp_extension.ts` **→ fix** `input`**,** `session_stop`**,** `user_python`**, and tool-rewrite semantics → add** `_[omp.py](http://omp.py)` **discovery → add pinned OMP compile/runner/discovery tests → make repo scope explicit before enabling global user installation.** That gets you an adapter whose correctness is anchored to what OMP actually runs, not to Slopgate's private reenactment of its API.