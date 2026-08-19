"""Install private-to-public module aliases before nested rule packages load."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from types import ModuleType


class _PublicModuleLoader(Loader):
    """Load a public module and publish it under a compatibility name."""

    def __init__(self, public_name: str) -> None:
        self.public_name = public_name

    def create_module(self, spec: ModuleSpec) -> ModuleType:
        if spec.name == "":
            raise ImportError("compatibility loader received an empty module name")
        if self.public_name == "":
            raise ImportError("compatibility loader is missing a public module name")
        return importlib.import_module(self.public_name)

    def exec_module(self, module: ModuleType) -> None:
        if module.__name__ == "":
            raise ImportError("compatibility loader cannot exec an unnamed module")
        return None


class PrivateNameFinder(MetaPathFinder):
    """Resolve deleted ``_prefix`` modules to their public replacements."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        public_name = self._mapping.get(fullname)
        if public_name is None:
            return None
        return ModuleSpec(fullname, _PublicModuleLoader(public_name))


def install_private_name_finder(mapping: dict[str, str]) -> None:
    """Register or merge *mapping* on ``sys.meta_path``."""
    for item in sys.meta_path:
        if isinstance(item, PrivateNameFinder):
            item._mapping.update(mapping)
            return
    sys.meta_path.insert(0, PrivateNameFinder(mapping))


def install_source_parse_alias() -> None:
    """Map ``_rules._source_parse`` onto ``_rules.source_parse``."""
    pkg = "slopgate.rules.python_ast._rules"
    install_private_name_finder({f"{pkg}._source_parse": f"{pkg}.source_parse"})
