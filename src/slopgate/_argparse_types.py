from __future__ import annotations

import argparse
from typing import Protocol


class SubparserRegistry(Protocol):
    """Structural type for objects that can register argparse subparsers."""

    def add_parser(
        self,
        name: str,
        **kwargs: object,
    ) -> argparse.ArgumentParser: ...
