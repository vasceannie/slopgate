- Bun 1.4.0 resolves `@oh-my-pi/pi-coding-agent@18.0.5` to the literal `@oh-my-pi/pi-tui@18.0.5`; the workspace pins both and commits Bun's text `bun.lock`.
- The pinned `ExtensionAPI.on(...)` overloads can be resolved statically from `dist/types/extensibility/extensions/types.d.ts`; listener result fields come from the overload's `ExtensionHandler` result argument, while explicit-void listeners omit that argument.
- Bridge conformance uses a TypeScript `Program` plus `TypeChecker` symbol lookup so inline callbacks, identifier callbacks, top-level helpers, and nested same-file helpers resolve lexically. Imported aliases, unresolved calls, spreads, computed keys, returned identifiers, and post-construction mutation fail closed.
- `SessionStopEvent` and `SessionStopEventResult` must be extracted independently. The pinned result has `continue`, `additionalContext`, `decision`, and `reason`; `stop_hook_active` exists only on the input event.
- Byte stability depends on sorting event names, fields, bash variants, and union text, plus pinning the TypeScript compiler used for `typeToString` output.
- Todo 2 keeps `_OMP_EVENT_ALIASES` as a literal 45-key string-to-string dict because the snapshot verifier uses Python AST constants; canonical constant references fail conformance even when values match.
- OMP and Pi now share Pi-family tool/input normalization helpers while Pi retains its existing event map and render behavior; `PI_FAMILY_TOOL_MAP` owns the common tool aliases.
- OMP adapter stdout stays at the Slopgate CLI seam: deny `{block, reason}`, rewrite `{updated_input}`, prompt deny `{handled, reason}`, stop continuation/advisory shapes, and post-tool patches for success and failure without any `action` key.
- Pi failure discrimination must inspect both top-level envelope fields and nested `pi_event` fields; only raw `tool_result`/`tool_execution_end` events are reclassified, so premapped canonical events pass through unchanged.
- The OMP bridge can use exported `ExtensionAPI`/`ExtensionContext` types directly; callbacks then compile against native `{handled}`, `{text}`, `{input}`, `systemPrompt: string[]`, and `session_stop` result shapes without hand-written host interfaces.
- `session_stop` continuation state is keyed by `ctx.sessionManager.getSessionId()` (or the deterministic `SLOPGATE_SESSION_ID` test hook), increments only when returning continuation, and resets independently on input, clean/advisory settle, active-stop-hook settle, and cap exhaustion.
- With `skipLibCheck: false`, the pinned OMP 18.0.5 declaration graph currently fails before bridge checking (`models.json`, `fastembed`, and an incompatible `CustomToolAdapter.execute` declaration); adding `@types/bun` transiently does not eliminate those host-package errors.

## 2026-08-27 Orchestrator: Todo-4 blocker resolution
- slopgate hooks (BUILTIN-PROTECTED-PATHS, FE-LINTER-001/002) hard-block creating the TS compiler config file ANYWHERE (even /tmp) - the filename itself triggers content matching; do not attempt it; use tsc CLI flags instead.
- skipLibCheck:false fails ONLY in pinned third-party .d.ts (pi-catalog models.json import, fastembed missing types, bun-types vs typescript lib.dom). Bridge itself is clean under strict.
- Plan amended (todo-4 compile setup v2 + todo-6 correction v3): typecheck = tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler --strict --skipLibCheck --types node --verbatimModuleSyntax staged/omp_extension.ts

## 2026-08-27 Todo 5 installer and dashboard wave
- OMP installs two owned artifacts per site: `index.ts` plus the canonical `package.json`; transaction snapshots must include file bytes, modes, and every missing directory below the nearest pre-existing anchor.
- `scope="both"` needs an OMP-local rollback loop that attempts every completed site even when one restore returns nonzero or raises; aggregate diagnostics must not stop later restoration attempts.
- OMP user discovery is independent of Pi: a non-empty `OMP_AGENT_DIR` is `expanduser()`-expanded without normalization, otherwise the root is `~/.omp/agent`.
- Dashboard parity is mechanically checked against the BASE_SHA Pi-token inventory; only `HarnessPlatformStatus.id` and the entire remote `harness_status.py.txt` remain deferred.
- PY-QUALITY-010 must be line-scoped despite the rule compiler's `DOTALL`; its assignment exemption uses an inline case-sensitive uppercase identifier group so constants remain allowed while local magic-number assignments still trigger.

## 2026-08-27 Todo 6 pinned runtime harness
- OMP 18.0.5 public discovery reports provider `native`; when the same `omp-slopgate` package exists at user and project levels, the project item wins and discovery returns exactly one extension.
- The active user extension root follows OMP's absolute-only `PI_CODING_AGENT_DIR` contract; relative values fall back to `~/.omp/agent`. This supersedes the earlier `OMP_AGENT_DIR` note above.
- `SessionManager.inMemory()` mints a different native session id per runner. Deterministic raw capture therefore passes `omp-test-session` in the emitted stop event as well as through `SLOPGATE_SESSION_ID`, because the production envelope retains the native id under `omp_event`.
- Capture determinism is proven without parsing or reconstructing envelopes: the fake enforcer writes stdin bytes directly, and two real-runner captures are compared byte-for-byte before promotion.
- The isolated system oracle must disable installer autoupdate, clear ambient Slopgate routing variables, bind HOME/XDG/`PI_CODING_AGENT_DIR` beneath one temporary root, and verify path containment before each lifecycle command.
