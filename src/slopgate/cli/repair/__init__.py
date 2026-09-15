"""OpenCode repair-gate commands.

Only the public command surface is re-exported. The scoped-lint verification core
lives in ``._verification``, state access in ``._scoping``, and the command bodies
in ``._commands``; internal names are deliberately not re-exported here so a stale
patch path such as ``slopgate.cli.repair._run_scoped_lint`` fails loudly instead of
silently binding an alias that no caller reads.
"""

from __future__ import annotations

__all__ = [
    "add_repair_parsers",
    "cmd_repair_clear",
    "cmd_repair_status",
    "cmd_repair_verify",
]
from ._commands import cmd_repair_clear, cmd_repair_status, cmd_repair_verify
from ._parser import add_repair_parsers
