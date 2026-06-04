from __future__ import annotations

import os
import sys
import warnings

from slopgate.cli.main import main
from slopgate.cli.parsers import build_parser
from slopgate.constants import EXIT_KEYBOARD_INTERRUPT

__all__ = ["build_parser", "main", "safe_main"]

_DEPRECATED_CLI_NAMES = frozenset({"vfc", "isx"})


def _warn_deprecated_cli() -> None:
    prog = os.path.basename(sys.argv[0]) if sys.argv else ""
    if prog not in _DEPRECATED_CLI_NAMES:
        return
    warnings.warn(
        f"'{prog}' is deprecated; use 'slopgate' or 'sgt' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        f"warning: '{prog}' is deprecated; use 'slopgate' or 'sgt' instead.",
        file=sys.stderr,
    )


def safe_main(argv: list[str] | None = None) -> int:
    _warn_deprecated_cli()
    try:
        return main(argv)
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT


if __name__ == "__main__":
    raise SystemExit(safe_main())
