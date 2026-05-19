from __future__ import annotations

_SCOPE_ORDER = {"function": 0, "class": 1, "module": 2, "package": 3, "session": 4}
_VALID_SCOPE_TEXT = "`function`, `class`, `module`, `package`, or `session`"


def fixture_scope_fragment(scope: str | None) -> str:
    if scope is None or scope == "function":
        return "function-scoped"
    return f"{scope}-scoped"


def is_unknown_fixture_scope(scope: str | None) -> bool:
    return scope is not None and scope not in _SCOPE_ORDER


def valid_fixture_scope_text() -> str:
    return _VALID_SCOPE_TEXT


def is_valid_fixture_loop_scope(scope: str | None, loop_scope: str | None) -> bool:
    if is_unknown_fixture_scope(scope) or is_unknown_fixture_scope(loop_scope):
        return False
    return _scope_order(loop_scope) >= _scope_order(scope)


def _scope_order(scope: str | None) -> int:
    return _SCOPE_ORDER.get(scope or "function", _SCOPE_ORDER["function"])
