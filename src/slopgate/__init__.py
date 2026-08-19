"""slopgate — global CLI guardrails engine for AI coding agents."""

from ._version import __version__
from .boot_aliases import install_source_parse_alias

install_source_parse_alias()

__all__ = ["__version__"]
