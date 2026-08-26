"""Public hashline projection boundary."""

from slopgate.util import logger

from . import hash
from .edits import apply_hashline_edits, project_hashline_edits


def line_hash(line_number: int, content: str, *, legacy: bool = False) -> str:
    """Return the OMO two-character line hash for one source line."""
    logger.debug("Public hashline helper requested", line=line_number, legacy=legacy)
    return hash.line_hash(line_number, content, legacy=legacy)


__all__ = ["apply_hashline_edits", "line_hash", "project_hashline_edits"]
