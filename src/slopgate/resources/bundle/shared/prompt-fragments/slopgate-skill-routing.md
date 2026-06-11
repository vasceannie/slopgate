# Slopgate skill routing

When Slopgate hooks, lint findings, quality gates, or user requests mention these topics, load **one primary skill first** before fixing code. Load secondary skills only when the primary skill explicitly says to escalate.

## Selection order

Prefer evidence in this order: exact rule ID or collector name → explicit hook recommendation → user request wording → code shape. Do not load a Slopgate skill only because the word "quality" appears.

1. `slopgate-hygiene-orchestrator`
   - Primary for: repo-wide or multi-file/multi-rule cleanup, bulk hook remediation, lint tracking, and "fix all Slopgate warnings" work.
   - Signals: `QUALITY-LINT-001` across multiple files, many collector findings, repeated hook denials, or `slopgate lint check --details` output that needs grouping.
   - Do not use for: a single local structural denial; use `slopgate-code-hygiene-refactor` instead.

2. `slopgate-code-hygiene-refactor`
   - Primary for: structural shape failures such as oversized modules/functions, god classes, flat sibling packages, complexity, type-suppression bans, and post-edit quality backstops.
   - Signals: `PY-CODE-017`, `PY-CODE-018`, `PY-CODE-014`, `QUALITY-LINT-001` on a touched file, module-size or complexity denials.
   - Do not use for: deciding whether an existing helper/constant already exists; use `slopgate-code-smell-utility-locator` first.

3. `slopgate-code-smell-utility-locator`
   - Primary for: finding existing helpers/constants/builders/factories before adding new ones, duplicate helpers, scattered utilities, feature envy, thin wrappers, magic numbers, and repeated literals.
   - Signals: `PY-CODE-012`, `PY-CODE-013`, `PY-CODE-009`, `PY-QUALITY-010`, duplicate helper reviews, or "where is this already implemented?"
   - Do not use for: broad package splits or oversized modules after ownership is already known; use `slopgate-code-hygiene-refactor`.

4. `slopgate-intelligent-coding-patterns`
   - Primary for: choosing a refactor pattern for branching/state/policy/dispatch/parser/transform code.
   - Signals: three or more branches, if/elif dispatch chains, boolean-flag state machines, repeated policy predicates, strategy/state/specification/pipeline/dispatch-table decisions.
   - Do not use for: simple two-branch cleanup, style-only edits, or pattern theater.

5. `slopgate-test-extender`
   - Primary for: missing test coverage, weak assertions, test-integrity failures, coverage holes, parametrization, or property-test guidance.
   - Signals: `untested-production-code`, `hypothesis-candidate`, `test-integrity`, `weak assertion`, `loop-to-parametrize`, "add tests", or "coverage hole".
   - Testing choice: use `pytest.mark.parametrize` for finite named examples and regressions; use Hypothesis for broad input domains and invariants; keep both when they serve different purposes.

## Escalation rules

- If hook output names a Slopgate skill, follow that recommendation unless the exact rule ID clearly points elsewhere.
- If multiple skills match, pick the earliest skill in the selection order whose trigger is exact. Do not load all five.
- If the first skill reveals a different primary problem, switch once and state why.
- Do not paste full skill bodies into prompts. This fragment is routing guidance only: load the named skill for the detailed workflow.
