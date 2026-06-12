---
name: slopgate-code-smell-utility-locator
description: |
  Autoactivate when code-smell hooks or reviews mention feature envy, thin wrappers, duplicate helpers, duplicate code,
  scattered helpers, builders/factories/config/constants/dataclass reuse, PY-CODE-012, PY-CODE-013, QUALITY-LINT-001,
  or repeated slopgate code-quality denials. Also load when asked to "find existing helpers", "consolidate utilities",
  "search for duplicate code", "where is this already implemented", "reuse existing logic", "don't duplicate this",
  "find similar functions", "utility inventory", "code smell radar", or before adding new helpers/wrappers so agents can
  find existing shared utilities and consolidate instead of duplicating.
version: 1.0.0
author: Slopgate
license: MIT
compatibility: claude-code, opencode, codex, hermes, slopgate
metadata:
  hermes:
    tags: [slopgate,code-smells,utilities,duplication,constants]
    related_skills: [slopgate-code-hygiene-refactor,slopgate-intelligent-coding-patterns]
  slopgate:
    rule_ids: [PY-CODE-012,PY-CODE-013,PY-CODE-009,PY-CODE-014,PY-CODE-018,PY-QUALITY-010,QUALITY-LINT-001]
    activation:
      primary: [helper discovery,constant ownership,duplicate utilities,feature envy,thin wrappers]
      avoid: [known package split,repo-wide lint coordination,test-only coverage]
---

# Code Smell Utility Locator

Use this skill before writing or retrying code after these smells appear:

- feature envy: logic belongs closer to the object or module it interrogates
- thin wrappers: a function/method only forwards arguments without adding policy, validation, caching, translation, logging, or a real boundary
- duplicate helpers/builders/factories/constants/configs/dataclasses
- repeated slopgate code-quality hook denials, especially `PY-CODE-012`, `PY-CODE-013`, `PY-CODE-009`, `PY-CODE-014`, `PY-CODE-018`, or `QUALITY-LINT-001`

## When to Use

Use before adding helpers, builders, factories, wrappers, constants, config objects, or dataclasses when existing ownership may already exist.

- Rule IDs include `PY-CODE-012`, `PY-CODE-013`, `PY-CODE-009`, `PY-QUALITY-010`, or reviews mention feature envy, thin wrappers, duplicate helpers, magic numbers, or repeated literals.
- User asks where logic already exists, whether to reuse a helper, or how to consolidate utilities.
- Load this before `slopgate-code-hygiene-refactor` when the main uncertainty is ownership, not file size.

## When Not to Use

Do not use for a known oversized module/package split after ownership is clear; use `slopgate-code-hygiene-refactor`.

Do not use for broad repo-wide cleanup coordination; use `slopgate-hygiene-orchestrator`.

Do not use for choosing a design pattern after utility ownership is already settled; use `slopgate-intelligent-coding-patterns`.

## Non-negotiable behavior

1. Search before creating a new helper, builder, factory, constants module, config object, dataclass, facade, or wrapper.
2. Prefer reusing or moving logic to an existing owner over adding another parallel utility.
3. Do not create a wrapper unless it adds a named boundary: validation, normalization, policy, permissions, logging, caching, retries, protocol adaptation, or third-party API shielding.
4. For feature envy, first inspect utilities and methods near the envied object/module before extracting a detached helper.
5. For duplicate code, consolidate at the closest stable boundary. Do not make a huge generic helper just to silence a smell.
6. Use the scripts to produce bounded evidence; do not dump an entire repo into context.

## Fast path

From any repository root, run the helper scripts from the skill directory that your harness loaded. Do not assume the Slopgate source checkout path exists.

```bash
# If your harness exposes the loaded skill directory, point SKILL_DIR at it.
# Otherwise use the symlinked harness skill path below.
python3 "$SKILL_DIR/scripts/utility_inventory.py" . --format text --limit 160
python3 "$SKILL_DIR/scripts/code_smell_radar.py" . --format text --limit 120
```

Common harness locations when the bundle manifest has been linked:

```bash
# Claude Code
SKILL_DIR="$HOME/.claude/skills/slopgate-code-smell-utility-locator"

# OpenCode
SKILL_DIR="$HOME/.config/opencode/skills/slopgate-code-smell-utility-locator"

# Codex / generic local skill mirror
SKILL_DIR="$HOME/.codex/skills/slopgate-code-smell-utility-locator"
```

If none of those paths exists, search the active harness skill directory for `slopgate-code-smell-utility-locator/SKILL.md` and use that parent directory. Keep the search bounded; do not crawl dependency directories.

## Script reference

### `utility_inventory.py`

Returns locations and signatures for likely shared utilities:

- helpers/utilities
- builders and factories
- constants
- config/settings classes and modules
- dataclasses / attrs / pydantic-style models
- facades and package re-export surfaces

Examples:

```bash
# Whole repo, bounded text output
python3 ~/.local/share/agent-skills/slopgate-code-smell-utility-locator/scripts/utility_inventory.py . --format text --limit 120

# Focus on a package and emit JSON for tooling
python3 ~/.local/share/agent-skills/slopgate-code-smell-utility-locator/scripts/utility_inventory.py src --format json --limit 500

# Narrow by category
python3 ~/.local/share/agent-skills/slopgate-code-smell-utility-locator/scripts/utility_inventory.py . --category builders --category factories
```

### `code_smell_radar.py`

Returns likely thin wrappers, feature envy candidates, duplicate signatures, duplicate normalized function bodies, and repeated helper names.

Examples:

```bash
python3 ~/.local/share/agent-skills/slopgate-code-smell-utility-locator/scripts/code_smell_radar.py . --format text --limit 120
python3 ~/.local/share/agent-skills/slopgate-code-smell-utility-locator/scripts/code_smell_radar.py . --format json --min-duplicate-size 4
```

Use this output as a map, not as a verdict. The correct fix still depends on architecture.

## Slopgate recovery loop

When slopgate fires the same code-smell hook twice on the same path/rule:

1. Stop retrying the patch.
2. Run `utility_inventory.py` on the nearest package or repository root.
3. Run `code_smell_radar.py` on the touched package.
4. Reread the target file and the closest existing utility owner.
5. Choose one of these outcomes:
   - reuse existing utility;
   - move behavior to the envied owner;
   - inline the thin wrapper;
   - extract a real boundary with named responsibility;
   - write a short note explaining why consolidation is unsafe right now.

## Output discipline

- Share only the top relevant paths/signatures in the conversation.
- If a script returns hundreds of results, rerun it with a narrower root/category.
- Do not paste raw secrets, environment files, or credential-bearing config. The scripts skip common secret/cache directories, but agents are still responsible for safe output.
