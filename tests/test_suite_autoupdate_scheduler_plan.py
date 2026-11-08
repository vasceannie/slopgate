from __future__ import annotations

import plistlib
from pathlib import Path
import pytest

import slopgate.installer._suite
from tests.support import SKIP_DARWIN_ONLY


@SKIP_DARWIN_ONLY
def test_macos_scheduler_plan_escapes_plist_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite, "is_windows", lambda: False)
    monkeypatch.setattr(slopgate.installer._suite.sys, "platform", "darwin")
    monkeypatch.setattr(
        slopgate.installer._suite, "find_binary", lambda: "/usr/local/bin/slopgate"
    )
    plan = slopgate.installer._suite.build_scheduler_plan(
        "git+https://example.invalid/vf.git?x=1&y=<two>"
    )
    parsed = plistlib.loads(plan.content.encode("utf-8"))
    assert (
        parsed["ProgramArguments"][-1]
        == "git+https://example.invalid/vf.git?x=1&y=<two>"
    )
