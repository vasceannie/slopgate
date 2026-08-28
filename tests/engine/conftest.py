"""Fixtures scoped to engine hook tests."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

import pytest

from slopgate._types import ObjectDict
from tests.engine.support import BUNDLE_ROOT, pretool_write_payload


@pytest.fixture
def remediation_write() -> Callable[[str, str], ObjectDict]:
    """Build same-session PreToolUse Write payloads for remediation cases."""

    return partial(pretool_write_payload, BUNDLE_ROOT)
