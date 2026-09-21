---
name: slopgate-eval-dataset
description: >
  Use the slopdata eval corpus and Slopgate gold fixtures for rule research,
  calibration, FP/FN hunting, and offline testing. Activate when working with
  slopdata datasets/v1, gold_*.json fixtures, slopgate eval, L1/L2/L3 packs,
  holdout replay, mine_gold_fixtures, or when asked how to test rules against
  historical OpenCode/Slopgate telemetry.
---

# Slopgate eval dataset

Paired telemetry lives in **`~/repos/slopdata`**. Slopgate vendors only gold + a tiny holdout. Full usage guide: `~/repos/slopdata/docs/USAGE.md` (also `docs/eval-dataset.md` in this repo).

## Choose the right artifact

| Intent | Artifact |
|--------|----------|
| Change a rule / adapter safely | `fixtures/gold_*.json` + `tests/test_eval_gold_fixtures.py` |
| Prove eval plumbing | `slopgate eval --pack tests/fixtures/eval/l1_ci.jsonl` (or `l1_holdout_pilot.jsonl`) |
| Current vs historical labels | `~/repos/slopdata/datasets/v1/overlays/l1-positives-current.jsonl` |
| Volume research on a rule | `~/repos/slopdata/datasets/v1/by_rule/l1/<RULE>.jsonl` |
| Deny-focused L1 (no TN flood) | `.../l1/eval-v1.positives.jsonl` |
| Repair success exploration | `.../l2/episodes-v1.benchmark.jsonl` |
| Post-deny agent trajectories | `.../l3/trajectories-v1.jsonl` or confirmed sidecar `.../overlays/l3-ground-truth.jsonl` |
| Global histograms | `.../v1/reports/calibration.json` |

**Never** fail CI on historical holdout label overlap. Gold = quality gate; history = research.

## Testing workflow

1. Prefer existing gold fixtures before inventing new synthetic fixtures.
2. After rule changes, run:
   ```bash
   uv run pytest tests/test_eval_gold_fixtures.py -q
   ```
3. If a gold primary rule no longer fires, either fix the regression or deliberately remine/update `_gold.current_rule_ids` (document why).
4. Expand coverage with:
   ```bash
   cd ~/repos/slopdata
   python3 scripts/mine_gold_fixtures.py --clear-existing --positives 150 --true-negatives 40
   ```
5. For pack smoke (not quality):
   ```bash
   uv run slopgate eval --pack tests/fixtures/eval/l1_holdout_pilot.jsonl --pretty
   ```

## Research workflow

1. Open `calibration.json` → pick hot `rule_id`.
2. Stream `by_rule/l1/<RULE>.jsonl` (do not load full `eval-v1.jsonl` into memory).
3. Filter `tier == replayable` for anything you might replay.
4. Replay via `slopgate.eval.evaluate_pack` or `evaluate_payload` on an **enrolled** temp repo (`slopgate.toml` present).
5. For repair questions, use L2 benchmark states `resolved` / `still_failing` (legacy; not authoritative).
6. For behavior-after-deny, use L3; quote `overlays/l3-ground-truth.jsonl` only for confirmed `outcome_ground_truth` rows.
7. Promote survivors into gold fixtures; add pytest coverage.

## Implementation checklist (wiring into Slopgate)

- [ ] Rule change → gold test still passes (or gold updated intentionally)
- [ ] New rule → at least one gold pos + one gold TN or clean near-miss
- [ ] OpenCode-specific behavior → fixture under `fixtures/opencode/`
- [ ] Docs: update `docs/eval-dataset.md` only if CLI/pack contracts change
- [ ] Do not commit raw `~/repos/slopdata/raw` or full v1 packs into the slopgate git repo

## Anti-patterns

- Loading 749k-row `eval-v1.jsonl` (mostly true negatives) in pytest
- Asserting historical `expected` equals current findings on holdout
- Quoting L3 heuristic outcome rates as product metrics
- Weakening gold assertions to green a broken detector
