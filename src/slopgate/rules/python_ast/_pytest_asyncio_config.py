from __future__ import annotations
import configparser
import importlib
import shlex
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, cast

_toml_loads: Callable[[str], object] | None = None
_toml_decode_error: type[Exception] | None = None
for _module_name in ("tomllib", "tomli"):
    try:
        _toml_module = importlib.import_module(_module_name)
    except ModuleNotFoundError:
        continue
    _loads = getattr(_toml_module, "loads", None)
    if callable(_loads):
        _toml_loads = cast(Callable[[str], object], _loads)
        _toml_decode_error = cast(
            type[Exception], getattr(_toml_module, "TOMLDecodeError", ValueError)
        )
        break
if TYPE_CHECKING:
    from slopgate.context import HookContext


class _PytestAsyncioConfig(NamedTuple):
    mode: str | None
    default_fixture_loop_scope: str | None


_CONFIG_PRIORITY = ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")
_INI_SECTIONS = ("pytest", "tool:pytest", "tool:pytest.ini_options")
_EMPTY_CONFIG = _PytestAsyncioConfig(None, None)


def _mapping_value(data: object, key: str) -> object | None:
    if not isinstance(data, Mapping):
        return None
    return cast("Mapping[str, object]", data).get(key)


def string_value(data: object) -> str | None:
    if not isinstance(data, str):
        return None
    stripped = data.strip().lower()
    return stripped or None


def _addopts_asyncio_mode(data: object) -> str | None:
    if isinstance(data, str):
        addopts = data
    elif isinstance(data, list):
        addopts_parts: list[str] = []
        for item in cast("list[object]", data):
            if not isinstance(item, str):
                return None
            addopts_parts.append(item)
        addopts = " ".join(addopts_parts)
    else:
        return None
    try:
        tokens = shlex.split(addopts)
    except ValueError:
        return None
    for index, token in enumerate(tokens):
        if token.startswith("--asyncio-mode="):
            return string_value(token.split("=", 1)[1])
        if token == "--asyncio-mode" and index + 1 < len(tokens):
            return string_value(tokens[index + 1])
    return None


def _pyproject_config(path: Path) -> _PytestAsyncioConfig | None:
    if _toml_loads is None or _toml_decode_error is None:
        return None
    try:
        data = _toml_loads(path.read_text(encoding="utf-8"))
    except (OSError, _toml_decode_error):
        return None
    tool = _mapping_value(data, "tool")
    pytest_section = _mapping_value(tool, "pytest")
    ini_options = _mapping_value(pytest_section, "ini_options")
    if not isinstance(ini_options, Mapping):
        return None
    options = cast("Mapping[str, object]", ini_options)
    return _PytestAsyncioConfig(
        _addopts_asyncio_mode(_mapping_value(options, "addopts"))
        or string_value(_mapping_value(options, "asyncio_mode")),
        string_value(_mapping_value(options, "asyncio_default_fixture_loop_scope")),
    )


def _ini_config(path: Path, *, recognize_empty: bool) -> _PytestAsyncioConfig | None:
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return _EMPTY_CONFIG if recognize_empty else None
    if not recognize_empty and (
        not any((parser.has_section(section) for section in _INI_SECTIONS))
    ):
        return None
    return _PytestAsyncioConfig(
        _ini_asyncio_mode(parser),
        _ini_option(parser, "asyncio_default_fixture_loop_scope"),
    )


def _ini_option(parser: configparser.ConfigParser, option_name: str) -> str | None:
    for section in _INI_SECTIONS:
        if parser.has_option(section, option_name):
            return string_value(parser.get(section, option_name))
    return None


def _ini_asyncio_mode(parser: configparser.ConfigParser) -> str | None:
    for section in _INI_SECTIONS:
        if parser.has_option(section, "addopts"):
            addopts_mode = _addopts_asyncio_mode(parser.get(section, "addopts"))
            if addopts_mode is not None:
                return addopts_mode
        if parser.has_option(section, "asyncio_mode"):
            return string_value(parser.get(section, "asyncio_mode"))
    return None


def _pytest_config_for_root(root_text: str) -> _PytestAsyncioConfig:
    root = Path(root_text)
    for config_name in _CONFIG_PRIORITY:
        path = root / config_name
        if not path.exists():
            continue
        if config_name == "pytest.ini":
            return _ini_config(path, recognize_empty=True) or _EMPTY_CONFIG
        if config_name == "pyproject.toml":
            config = _pyproject_config(path)
        else:
            config = _ini_config(path, recognize_empty=False)
        if config is not None:
            return config
    return _EMPTY_CONFIG


def pytest_asyncio_mode(ctx: HookContext) -> str | None:
    return _pytest_config_for_root(str(ctx.config.repo_root)).mode


def pytest_asyncio_default_fixture_loop_scope(ctx: HookContext) -> str | None:
    return _pytest_config_for_root(str(ctx.config.repo_root)).default_fixture_loop_scope
