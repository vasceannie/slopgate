from __future__ import annotations

from slopgate.context import HookContext
from slopgate.models import RuleFinding

_IMPORT_ALIAS_EXAMPLES = (
    "Only canonical library aliases are allowed, e.g. `pandas as pd`, "
    "`polars as pl`, `numpy as np`, or `matplotlib.pyplot as plt`."
)
_IMPORT_ALIAS_EXAMPLES_KEY = "py-import-002-alias-examples"
_IMPORT_ALIAS_REPEAT_TEXT = (
    "Canonical alias examples were shown earlier this session; keep the exact "
    "replacement below."
)


def compress_repeated_import_alias_examples(
    ctx: HookContext, item: RuleFinding
) -> None:
    message = item.message
    if item.rule_id != "PY-IMPORT-002" or message is None:
        return
    if _IMPORT_ALIAS_EXAMPLES not in message:
        return
    state_key = f"{ctx.session_id}:{_IMPORT_ALIAS_EXAMPLES_KEY}"
    if ctx.state.should_emit_search_reminder(state_key):
        ctx.state.record_search_reminder(state_key)
        return
    item.message = message.replace(
        _IMPORT_ALIAS_EXAMPLES,
        _IMPORT_ALIAS_REPEAT_TEXT,
    )
