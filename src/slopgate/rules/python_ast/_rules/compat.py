"""Register public AST rule modules under former private import names."""

from __future__ import annotations

import sys
import types
from types import ModuleType


def _alias(name: str, module: ModuleType) -> None:
    """Publish *module* under a compatibility import name."""
    sys.modules[name] = module


def install_private_module_aliases() -> None:
    """Map ``_prefix`` import paths onto the public replacement modules."""
    from . import ast_health, broad_silent, complexity_dead, feature_envy
    from . import class_shape, sibling_files, style_limits
    from .log_signals import classify, constants, kinds, requirement

    pkg = __package__
    if pkg is None:
        return
    replacements = (
        (f"{pkg}._ast_health", ast_health),
        (f"{pkg}._broad_silent", broad_silent),
        (f"{pkg}._complexity_dead", complexity_dead),
        (f"{pkg}._feature_envy", feature_envy),
        (f"{pkg}._flat_siblings", sibling_files),
        (f"{pkg}._method_style", style_limits),
        (f"{pkg}.wrapper_god", class_shape),
        (f"{pkg}.method_style", style_limits),
        (f"{pkg}.flat_siblings", sibling_files),
    )
    for name, module in replacements:
        _alias(name, module)
    helpers = types.ModuleType(f"{pkg}._boundary_helpers")
    exported = (constants, classify, kinds)
    for src in exported:
        public_names = [attr for attr in dir(src) if not attr.startswith("_")]
        for attr in public_names:
            setattr(helpers, attr, getattr(src, attr))
    _alias(f"{pkg}._boundary_helpers", helpers)
    _alias(f"{pkg}._boundary_rule", requirement)
    from slopgate.boot_aliases import install_private_name_finder

    install_private_name_finder({f"{pkg}._wrapper_god": f"{pkg}.class_shape"})
