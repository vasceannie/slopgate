"""Shared rule interoperability metadata for dashboard scripts."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent.parent
SRC_DIR = REPO_ROOT / "src"


def load_rule_counterparts() -> dict[str, list[str]]:
    src_dir_text = str(SRC_DIR)
    if SRC_DIR.exists() and src_dir_text not in sys.path:
        sys.path.insert(0, src_dir_text)
    try:
        from slopgate.lint._parity import HOOK_RULE_BASELINE_COUNTERPARTS
    except ImportError:
        return {}
    return {
        rule_id: list(counterparts)
        for rule_id, counterparts in HOOK_RULE_BASELINE_COUNTERPARTS.items()
    }
