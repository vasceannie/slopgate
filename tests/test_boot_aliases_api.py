"""Contract for early private-to-public module alias installation."""

from __future__ import annotations

import importlib

from slopgate.boot_aliases import install_source_parse_alias

SOURCE_PARSE_PRIVATE = "slopgate.rules.python_ast._rules._source_parse"
SOURCE_PARSE_PUBLIC = "slopgate.rules.python_ast._rules.source_parse"


def test_private_source_parse_alias_shares_parse_strict() -> None:
    install_source_parse_alias()
    private = importlib.import_module(SOURCE_PARSE_PRIVATE)
    public = importlib.import_module(SOURCE_PARSE_PUBLIC)
    assert private.parse_strict is public.parse_strict


def test_install_source_parse_alias_is_idempotent() -> None:
    first = install_source_parse_alias()
    second = install_source_parse_alias()
    assert (first, second) == (None, None)
