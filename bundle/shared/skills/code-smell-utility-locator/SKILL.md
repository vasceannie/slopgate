---
name: code-smell-utility-locator
description: |
  Autoactivate when code-smell hooks or reviews mention feature envy, thin wrappers, duplicate helpers, duplicate code,
  scattered helpers, builders/factories/config/constants/dataclass reuse, PY-CODE-012, PY-CODE-013, QUALITY-LINT-001,
  or repeated slopgate code-quality denials. Use the bundled scripts before adding new helpers/wrappers so agents can
  find existing shared utilities and consolidate instead of duplicating.
license: MIT
compatibility: claude-code, opencode, codex, hermes, slopgate
metadata:
  category: code-quality
  autoactivation: code-smell-hooks
  rule_ids: PY-CODE-012,PY-CODE-013,PY-CODE-009,PY-CODE-014,PY-CODE-018,QUALITY-LINT-001
---

# Code Smell Utility Locator

Use this skill before writing or retrying code after these smells appear:

- feature envy: logic belongs closer to the object or module it interrogates
- thin wrappers: a function/method only forwards arguments without adding policy, validation, caching, translation, logging, or a real boundary
- duplicate helpers/builders/factories/constants/configs/dataclasses
- repeated slopgate code-quality hook denials, especially `PY-CODE-012`, `PY-CODE-013`, `PY-CODE-009`, `PY-CODE-014`, `PY-CODE-018`, or `QUALITY-LINT-001`

## Non-negotiable behavior

1. Search before creating a new helper, builder, factory, constants module, config object, dataclass, facade, or wrapper.
2. Prefer reusing or moving logic to an existing owner over adding another parallel utility.
3. Do not create a wrapper unless it adds a named boundary: validation, normalization, policy, permissions, logging, caching, retries, protocol adaptation, or third-party API shielding.
4. For feature envy, first inspect utilities and methods near the envied object/module before extracting a detached helper.
5. For duplicate code, consolidate at the closest stable boundary. Do not make a huge generic helper just to silence a smell.
6. Use the scripts to produce bounded evidence; do not dump an entire repo into context.

## Fast path

From any repository root:

```bash
python3 ~/.claude/skills/code-smell-utility-locator/scripts/utility_inventory.py . --format text --limit 160
python3 ~/.claude/skills/code-smell-utility-locator/scripts/code_smell_radar.py . --format text --limit 120
```

OpenCode users can run the same scripts through the global OpenCode skill path:

```bash
python3 ~/.config/opencode/skills/code-smell-utility-locator/scripts/utility_inventory.py . --format text --limit 160
python3 ~/.config/opencode/skills/code-smell-utility-locator/scripts/code_smell_radar.py . --format text --limit 120
```

Codex users should use the canonical path if shell expansion is available:

```bash
python3 ~/.local/share/agent-skills/code-smell-utility-locator/scripts/utility_inventory.py . --format text --limit 160
python3 ~/.local/share/agent-skills/code-smell-utility-locator/scripts/code_smell_radar.py . --format text --limit 120
```

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
python3 ~/.local/share/agent-skills/code-smell-utility-locator/scripts/utility_inventory.py . --format text --limit 120

# Focus on a package and emit JSON for tooling
python3 ~/.local/share/agent-skills/code-smell-utility-locator/scripts/utility_inventory.py src --format json --limit 500

# Narrow by category
python3 ~/.local/share/agent-skills/code-smell-utility-locator/scripts/utility_inventory.py . --category builders --category factories
```

### `code_smell_radar.py`

Returns likely thin wrappers, feature envy candidates, duplicate signatures, duplicate normalized function bodies, and repeated helper names.

Examples:

```bash
python3 ~/.local/share/agent-skills/code-smell-utility-locator/scripts/code_smell_radar.py . --format text --limit 120
python3 ~/.local/share/agent-skills/code-smell-utility-locator/scripts/code_smell_radar.py . --format json --min-duplicate-size 4
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
