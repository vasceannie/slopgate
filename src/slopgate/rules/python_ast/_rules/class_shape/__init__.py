"""Detect thin wrappers and god classes in Python AST."""

from .calls import (
    is_exempt_cast_wrapper,
    is_exempt_test_helper_wrapper,
    is_test_helper_path,
    is_wrapper_candidate,
    thin_wrapper_attribute_name,
    thin_wrapper_call_root_name,
    thin_wrapper_call_target_name,
    thin_wrapper_extract_single_call,
    thin_wrapper_has_self_or_cls_receiver,
)
from .god import PythonGodClassRule
from .thin import PythonThinWrapperRule
