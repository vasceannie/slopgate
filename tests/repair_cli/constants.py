"""Constants for repair CLI tests."""

from __future__ import annotations

GENERATION_ONE = "generation-one"
GENERATION_TWO = "generation-two"
REPAIR_PATH = "src/app.py"
DECOY_PATH = "src/huge.py"
COMPLEXITY_RULE = "PY-CODE-015"
CLEAN_SOURCE = (
    "from __future__ import annotations\n\n\ndef answer() -> int:\n    return 1\n"
)
OVERSIZED_FILLER_LINES = 370
OVERSIZED_SOURCE = (
    "from __future__ import annotations\n" + "# filler\n" * OVERSIZED_FILLER_LINES
)
SLOPGATE_TOML = "[slopgate]\nenabled = true\n"
