from __future__ import annotations

from tests.test_engine import WriteBuilder, evaluate_payload, finding_ids, pytest


@pytest.mark.parametrize(
    "constant_declaration",
    [
        pytest.param("TRACE_TEXT_LIMIT = 1000", id="plain-constant"),
        pytest.param("TRACE_TEXT_LIMIT: Final = 1000", id="annotated-constant"),
    ],
)
def test_py_quality_010_allows_named_constants_after_imports(
    pretool_write: WriteBuilder, constant_declaration: str
) -> None:
    code = f"from typing import Final\n{constant_declaration}\n"

    result = evaluate_payload(pretool_write("src/numbers.py", code))

    assert "PY-QUALITY-010" not in finding_ids(result), (
        f"Named constants should not trigger PY-QUALITY-010:\n{code}"
    )
