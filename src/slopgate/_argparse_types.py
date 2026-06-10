from __future__ import annotations

import argparse
from typing import Protocol


class SubparserRegistry(Protocol):
    """Structural type for objects that can register argparse subparsers."""

    def add_parser(
        self,
        name: str,
        *,
        help: str | None = None,
        description: str | None = None,
        formatter_class: type[argparse.HelpFormatter] = argparse.HelpFormatter,
    ) -> argparse.ArgumentParser: ...
