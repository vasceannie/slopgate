from __future__ import annotations

import pytest

from vibeforcer.search.completions import print_completion
from vibeforcer.search.config import IsxError


@pytest.mark.parametrize(
    ("shell", "expected_fragment"),
    [
        ("bash", "complete -F _isx isx"),
        ("zsh", "#compdef isx"),
    ],
)
def test_print_completion_writes_known_shell_script(
    shell: str,
    expected_fragment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = print_completion(shell)

    assert result == 0
    assert expected_fragment in capsys.readouterr().out


def test_print_completion_rejects_unknown_shell() -> None:
    with pytest.raises(IsxError, match="unsupported shell: fish"):
        print_completion("fish")
