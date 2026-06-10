from __future__ import annotations
import importlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast
from slopgate.util import warning
from ._coerce import object_dict

_toml_loads: Callable[[str], object] | None = None
for module_name in ("tomllib", "tomli"):
    try:
        _module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        continue
    if callable(getattr(_module, "loads", None)):
        _toml_loads = cast(Callable[[str], object], getattr(_module, "loads"))
        break


def load_toml(root: Path) -> dict[str, object]:
    """Load slopgate.toml from project root if available."""
    if _toml_loads is None:
        return {}
    for name in ("slopgate.toml",):
        toml_path = root / name
        if toml_path.exists():
            try:
                parsed = _toml_loads(toml_path.read_text(encoding="utf-8"))
                return object_dict(parsed)
            except (OSError, ValueError) as exc:
                warning(
                    "quality gate TOML load failed", path=str(toml_path), error=str(exc)
                )
                return {}
    return {}


def load_json(path: Path) -> dict[str, object]:
    try:
        parsed = cast(object, json.loads(path.read_text(encoding="utf-8")))
        return object_dict(parsed)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        warning("quality gate JSON load failed", path=str(path), error=str(exc))
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def slopgate_path(root: Path) -> Path:
    return root / "slopgate.toml"


def slopgate_template() -> str:
    from slopgate.lint import __version__
    from slopgate.lint._updater import render_slopgate_toml

    return render_slopgate_toml(version=__version__)


def write_slopgate(root: Path, template: str) -> bool:
    marker = slopgate_path(root)
    if marker.exists():
        return False
    root.mkdir(parents=True, exist_ok=True)
    _ = marker.write_text(template, encoding="utf-8")
    return True
