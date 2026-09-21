# Eval dataset (slopdata)

Slopgate’s offline evaluation corpus is built from paired OpenCode + Slopgate telemetry in **`~/repos/slopdata`**. This repo only vendors:

| Asset | Path | Role |
|-------|------|------|
| Gold fixtures | `fixtures/gold_*.json`, `fixtures/{opencode,codex,cursor,pi,omp}/gold_*.json` | Current-engine CI gate (212), parametrized by platform/rule |
| Pinned holdout | `tests/fixtures/eval/l1_holdout_pilot.jsonl` | Eval smoke (historical; not a quality gate) |
| CI slice | `tests/fixtures/eval/l1_ci.jsonl` | Stratified 300-row plumbing pack |
| Loader / CLI | `src/slopgate/eval/`, `slopgate eval --overlay-out` | Replay packs; sidecar writer |
| Tests | `tests/test_eval_gold_fixtures.py`, `tests/test_eval_dataset_pilot.py` | — |

**Full packs, per-rule dumps, L2/L3, and calibration reports** live under `~/repos/slopdata/datasets/v1/`.

## How to use

Read the canonical guide:

**[`~/repos/slopdata/docs/USAGE.md`](../../../../slopdata/docs/USAGE.md)**  
(if cloned as a sibling of this repo: `../slopdata/docs/USAGE.md`)

Quick commands:

```bash
# CI-oriented
uv run pytest tests/test_eval_gold_fixtures.py -q

# Smoke
uv run slopgate eval --pack tests/fixtures/eval/l1_holdout_pilot.jsonl --pretty
uv run slopgate eval --pack tests/fixtures/eval/l1_ci.jsonl --limit 20 --pretty --overlay-out /tmp/ci-overlay.jsonl

# Research pack (from slopdata)
uv run slopgate eval --pack ~/repos/slopdata/datasets/v1/by_rule/l1/SHELL-001.jsonl --limit 100 --pretty
```

## Agent skill

Use the Cursor/agent skill **`slopgate-eval-dataset`** when researching rules from historical packs, mining gold fixtures, or wiring eval into tests. See [`.cursor/skills/slopgate-eval-dataset/SKILL.md`](../.cursor/skills/slopgate-eval-dataset/SKILL.md).

## Rebuild

```bash
cd ~/repos/slopdata && make full
```
