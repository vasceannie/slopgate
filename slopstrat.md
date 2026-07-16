## Conclusion

Your hooks are not failing—the **feedback loop is**. Slopgate often identifies the right problem, but too much guidance arrives after mutation, repeated attempts are tracked too narrowly, and static instructions are less salient than the agent’s immediate coding impulse.

The highest-leverage change is to replace “deny, explain, retry” with:

**task-specific preflight → one coherent edit → projected validation → post-edit backstop**

Your 54.7% first-time resolution rate should be the primary optimization target. Lowering the number of blocks would risk weakening quality; raising first-time resolution above roughly 75% would reduce development time without relaxing standards.

I reviewed the packed repository and traced the relevant indexed implementation through MCP Proxy/GitNexus. 

## Findings

| Severity     | Type                       | Finding                                                                                                                                                                                                                                              | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Why it matters                                                                                                                                                                                     | Recommended fix                                                                                                                                                                                                                                            |
| ------------ | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | **accidental loophole**    | Retry enforcement identifies an attempt by an exact content/tool-input hash, while reporting identifies churn by rule, session, and path. Tiny patch changes therefore evade the runtime retry lock while still constituting the same failed design. | The fingerprint includes target-content hashes and the entire tool input in `src/slopgate/engine/_retry.py:43-70`. Deny-state keys include that fingerprint in `src/slopgate/state/_keys.py:155-174`. A changed fingerprint bypasses an existing retry lock in `src/slopgate/engine/_retry.py:233-248`. Stats aggregate more broadly in `src/slopgate/stats/_analysis.py:125-145`.                                                                                             | This explains how a session can accumulate 296 denials of one rule despite having retry-budget enforcement. Agents can keep making semantically equivalent edits that appear technically distinct. | Maintain two counters: an exact-attempt fingerprint for diagnostics and a semantic churn key of `repo + session + rule + normalized path`. Lock after the second semantic recurrence, regardless of patch hash. Clear it only after the rule stops firing. |
| **High**     | **confirmed behavior**     | The strongest general guidance is injected as static prompt-context files on `UserPromptSubmit`, rather than being generated for the actual target, task, and likely rules.                                                                          | `PromptContextRule` loads and joins all configured fragments on prompt submission in `src/slopgate/rules/common/_shell_read.py:81-105`. The bundled hot-rule preflight is a fixed list in `src/slopgate/resources/prompt_context/repo.md:53-62`.                                                                                                                                                                                                                               | A large static rulebook competes with the feature request for model attention. It teaches the rules but does not force the agent to apply them to the file it is about to edit.                    | Generate a compact **First-Write Contract** containing the target path, reused pattern, predicted hot rules, design choices, and one verification command. Inject only the three to five relevant rules.                                                   |
| **High**     | **confirmed behavior**     | `QUALITY-LINT-001`, your largest source of denials, is inherently post-edit.                                                                                                                                                                         | `PostEditLintRule` handles only `PostToolUse`, evaluates files after mutation, and optionally blocks in `src/slopgate/rules/common/quality/lint.py:215-260`.                                                                                                                                                                                                                                                                                                                   | The agent cannot avoid many collector failures “on the first try” when the first authoritative evaluation occurs after the edit has landed.                                                        | Run high-frequency lint collectors against the proposed content before mutation. Keep the current post-edit rule as a backstop.                                                                                                                            |
| **High**     | **accidental loophole**    | A retry lock can be cleared using keyword recognition rather than verified corrective action.                                                                                                                                                        | `capture_repair_plan_signal` looks for “repair plan,” then basic “rule/constraint” and “read/reread” words in `src/slopgate/engine/_retry.py:305-313`. The state records only two booleans in `src/slopgate/state/_locks_store.py:65-81`. A qualifying plan clears the lock in `src/slopgate/engine/_retry.py:239-241`.                                                                                                                                                        | An agent can satisfy the protocol linguistically without actually rereading the target or changing its design.                                                                                     | Require recorded evidence: a target read after the lock timestamp, the actual locked rule IDs and paths in a structured plan, and a semantically different repair strategy.                                                                                |
| **High**     | **confirmed behavior**     | Repeated-failure memory is session-scoped and short-lived, despite stats showing persistent patterns across many sessions.                                                                                                                           | Session-start guidance retrieves failures only for the current session in `src/slopgate/engine/_retry.py:198-225`. The state query filters on the current session ID in `src/slopgate/state/_keys.py:214-236`. The disk state has a one-hour TTL in `src/slopgate/state/_locks_store.py:90-94`.                                                                                                                                                                                | Every new agent session can relearn the same lessons from scratch. Your aggregate statistics know which rules are hot, but runtime steering does not use that knowledge.                           | Maintain a decayed, repo-scoped failure profile by language, path role, platform, and model. Inject the top recurring failure patterns at session start and before the first mutation.                                                                     |
| **Medium**   | **documentation mismatch** | Universal replan guidance can conflict with rule-specific guidance, especially for thin wrappers.                                                                                                                                                    | The generic repeated-denial prompt recommends “small helper extractions” in `src/slopgate/engine/_hints/constants.py:2-6` and is appended to repeated denials in `src/slopgate/engine/_retry.py:128-138`. The `PY-CODE-013` guidance instead says to inline pass-throughs or add genuine policy in `src/slopgate/engine/_hints/constants.py:22-34`. The architecture rules also caution against unnecessary extraction in `bundle/claude/rules/quality-architecture.md:11-16`. | An agent denied for creating a thin wrapper can respond by extracting another helper, creating further churn.                                                                                      | Replace the universal replan text with rule-specific repair playbooks. Generic instructions should say “change the design,” not prescribe extraction.                                                                                                      |
| **Medium**   | **confirmed behavior**     | `PY-LOG-002` can classify functions as boundaries from path, class name, function name, or call markers, even without proving an actual runtime handoff.                                                                                             | Boundary paths and suffixes are enumerated in `src/slopgate/rules/python_ast/_rules/_boundary_helpers.py:35-51`. Any one of several signals can establish boundary status in `src/slopgate/rules/python_ast/_rules/_boundary_helpers.py:155-173`. Public functions without logging are then reported in `src/slopgate/rules/python_ast/_rules/_boundary_rule.py:110-133`.                                                                                                      | **Unverified false-positive rate**, but 1,743 denials make this a strong calibration candidate. Pure helpers inside `adapters/` or `repositories/` may be treated like real external handoffs.     | Make an observed outbound/event call blocking evidence. Treat path-, name-, or class-only classification as advisory unless the repository explicitly opts into strict boundary logging.                                                                   |

## Detailed analysis

### 1. The retry budget protects against identical patches, not persistent bad reasoning

The current design records an edit fingerprint containing the content hash and complete tool input. That is appropriate for stopping an agent from submitting the exact same patch repeatedly, but it is too precise for detecting brute-force behavior. A renamed helper, changed whitespace, or slightly altered wrapper creates a new fingerprint even when the same architectural mistake remains. `src/slopgate/engine/_retry.py:43-70`

The statistics subsystem already uses the more meaningful identity: same session, same rule, and often the same path. `src/slopgate/stats/_analysis.py:125-145` That is why the report sees enormous loops that the runtime lock does not effectively stop.

The runtime should track:

```text
exact attempt:
(session, rule, path, content fingerprint)

semantic churn:
(repo, session, rule, path)
```

The exact key answers, “Did the agent repeat the same patch?” The semantic key answers, “Is the agent still failing to understand the same invariant?”

After the second semantic hit, the next write should be denied until the agent has:

1. Reread the complete target.
2. Named the violated invariant.
3. Identified why the previous design failed.
4. Selected a rule-specific alternative.
5. Run any needed structural lookup.

The lock should not clear merely because the patch text changed.

### 2. Convert the static rulebook into a target-specific preflight

The repository prompt already contains valuable advice, and the dedicated Python executor has a strong pre-write scouting process: inspect the target and sibling patterns, assess likely hook risks, make one minimal patch, and run focused verification. `bundle/claude/agents/agent-python-executor.md:133-150`

The problem is delivery. The manifest installs that executor as an available agent asset, but no automatic runtime selection mechanism was found in the reviewed routing paths. `bundle/manifest.yaml:106-111` **Unverified:** another harness-level configuration outside the repository could select it automatically.

Instead of only telling the model about every rule, force it to produce a small artifact before its first write:

```text
PRE-WRITE CONTRACT
Target:
Existing pattern to reuse:
Public API or behavior being preserved:
Likely hook risks:
Design chosen to avoid them:
Focused verification:
```

This changes the model’s job from “remember dozens of rules while coding” to “apply five explicit constraints to this edit.”

The contract can be generated automatically from:

* Path role: source, test, adapter, repository, CLI, quality harness.
* Current file metrics: lines, methods, parameters, import shape.
* Proposed operation: new behavior, refactor, test addition, module split.
* Historical hot rules for that repository and model.
* GitNexus context or impact results for shared symbols.

### 3. Move predictable post-edit failures into pre-edit projection

Your highest-volume rule is `QUALITY-LINT-001`, but its implementation intentionally evaluates after the mutation. `src/slopgate/rules/common/quality/lint.py:215-260`

Not every collector can safely run before the write. However, many of the highest-friction collectors can evaluate a virtual file created from the proposed patch:

* Long methods and excessive parameters.
* Thin wrappers.
* Oversized modules.
* Flat sibling proliferation.
* Private import chains and aliases.
* Long lines and repeated literals.
* Direct logger creation.
* Common test smells.

A useful model is:

```text
PreToolUse:
    Evaluate proposed file overlay.
    Deny predictable structural violations before disk mutation.

PostToolUse:
    Format.
    Run filesystem-, project-, and cross-file-dependent collectors.
    Block only unexpected residual failures.
```

This is better than simply weakening `QUALITY-LINT-001`. The post-edit check remains authoritative, but fewer preventable defects reach it.

You should also support an **atomic edit burst**. The repository already warns that imports and their usages must be edited together because post-tool formatting can remove temporarily unused imports. `bundle/claude/rules/tool-atomic-edits.md:3-7` A coherent multi-part patch should incur one projected evaluation and one post-edit backstop, rather than many tiny mutation cycles.

### 4. Replace performative repair plans with state-backed recovery

The current repair-plan unlock is easy for a language model to game because it is itself linguistic. `src/slopgate/engine/_retry.py:305-313`

A structured recovery event should contain:

```json
{
  "target_paths": ["src/example.py"],
  "locked_rules": ["PY-CODE-013"],
  "files_reread_after_lock": ["src/example.py"],
  "violated_invariant": "The helper is a single-call pass-through.",
  "previous_design_failure": "Renaming it did not add policy or behavior.",
  "new_design": "Inline it into the caller and preserve the public facade.",
  "verification": "focused test node"
}
```

Slopgate can validate most of this mechanically. The model still writes the reasoning, but it cannot unlock itself merely by mentioning the right phrases.

### 5. Calibrate rule guidance before relaxing enforcement

The `PY-CODE-013` conflict is an important example. The universal recovery prompt recommends extraction, but the specific rule often requires inlining. `src/slopgate/engine/_hints/constants.py:2-6` `src/slopgate/engine/_hints/constants.py:22-34`

Use rule-specific repair verbs:

| Rule               | Preferred first response                                               |
| ------------------ | ---------------------------------------------------------------------- |
| `PY-CODE-013`      | Inline, absorb into owner, or add real validation/policy               |
| `PY-IMPORT-002`    | Remove invented alias; use canonical symbol name                       |
| `PY-IMPORT-003`    | Add/use public package facade                                          |
| `PY-LOG-002`       | Identify the actual handoff and use the existing telemetry abstraction |
| `PY-CODE-018`      | Split by responsibility with a stable facade                           |
| `QUALITY-LINT-001` | Repair only the named collector before resuming feature work           |
| `SHELL-001`        | Preserve errors and explicitly branch on expected failure              |

Do not give every structural failure the same “extract helpers” treatment.

For `PY-LOG-002`, sample at least 100 recent denials and classify them as:

* Real external/event boundary missing telemetry.
* Pure helper accidentally classified because of location/name.
* Existing telemetry not recognized.
* Test or generated code.
* Legitimate exception.

Its false-positive rate is currently **Unverified**. Given the path-based heuristic and denial volume, it should be measured before deciding whether to retain blocking severity for all detected boundary kinds. `src/slopgate/rules/python_ast/_rules/_boundary_helpers.py:155-173`

## Immediate agent steering template

The following can be installed in the repo-level orchestrator instructions and used before dispatching coding work. It is consistent with the existing executor’s pre-write and recovery model. `bundle/claude/agents/agent-python-executor.md:131-158`

## Repository Coding Protocol

Before the first repository mutation, produce a **Pre-Write Contract** containing:

* **Target:** exact files and symbols to change.
* **Reuse:** the nearest existing implementation, public facade, fixture, logger, or package pattern being reused.
* **Constraints:** the three to five Slopgate rules most likely to apply.
* **Design:** how the proposed implementation stays within those constraints.
* **Verification:** the smallest focused test, lint, or type-check command that proves the change.

For shared, public, or architectural symbols, inspect callers and impact before editing.

Make one coherent atomic edit. Batch imports with their usages and batch related source and test updates when partial intermediate states would be invalid.

Treat hook responses as follows:

* A **PreToolUse deny** means the mutation did not occur. Do not repeat the same design with cosmetic changes.
* A **PostToolUse block** means the mutation may have landed. Reread the touched file before repairing it.
* Advisory context should influence the design, but it is not a reason to rewrite otherwise-valid code.
* After the first denial, state the violated invariant and choose a materially different repair.
* After the same rule affects the same path twice, stop mutations. Reread the target and produce:

  1. the violated invariant;
  2. why the prior design failed;
  3. the different design that will be used next.

Do not attempt a third mutation until that recovery plan is complete.

Run focused verification after the coherent edit. Run repository-wide Slopgate lint only at a meaningful checkpoint, not after every micro-edit.

This protocol should be an enforced repo-level workflow step, not merely optional prose hidden among general instructions.

## Policy Boundary Recommendations

Slopgate’s existing enrollment model is directionally correct. Runtime mode separates `outside_repo`, `repo_strict`, and `repo_relaxed`, and repo-strict rules run only for enrolled repositories. `src/slopgate/engine/_runner.py:199-230` Enrollment and opt-out are determined through ancestor `slopgate.toml`, disable sentinels, and `[slopgate] enabled = false`. `src/slopgate/config/_repo.py:149-183`

Preserve that boundary while making these changes:

| Environment                 | Recommended enforcement                                                                                                                                                                                                                              |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Project repo work**       | Enable target-specific preflight, semantic churn locking, projected lint, cross-session repo failure profiles, post-edit quality gates, and rule-specific recovery. Blocking is appropriate for high-confidence violations.                          |
| **General workstation use** | Keep coding-quality rules inactive. Do not apply semantic retry locks, logger conventions, import architecture, module-size limits, test-smell rules, or completion gates outside explicitly enrolled repositories.                                  |
| **Server operations**       | Keep only narrow destructive-action, secret-access, and genuine system-protection controls globally active. Legitimate administration must have an explicit approval or admin escape hatch rather than being forced through repo coding conventions. |

The current always-on group is already limited to protected paths, sensitive data, and system protection, while prompt, git, lint, stop, AST, and regex quality rules are repo-strict. `src/slopgate/rules/__init__.py:195-236` Do not solve agent coding friction by expanding the repo rule set globally.

New mechanisms should follow these scope rules:

* The historical failure profile must be **repo-keyed**, never a universal profile applied across unrelated work.
* Predictive lint and semantic retry locks must activate only in `repo_strict`.
* `PY-LOG-002`, import architecture, code-size, tests, and completion rules must remain inactive during ordinary workstation and server administration.
* Global system-path protection should distinguish dangerous mutations from legitimate read-only inspection and authorized administrative changes.
* Degraded platforms need persistent repo instructions because not every harness can enforce every lifecycle hook equally; platform capability handling already distinguishes OpenCode, Codex, and Cursor limitations. `src/slopgate/engine/_runner.py:69-91`

The desired outcome is not fewer guardrails. It is **earlier, narrower, evidence-backed guidance inside managed repositories, with minimal interference everywhere else**.
