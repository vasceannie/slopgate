"""Classify event and package boundaries for observability rules."""

from .classify import (
    attribute_chain_parts,
    called_name,
    contains_event_boundary_call,
    function_name_has_event_signal,
    has_boundary_log_call,
    is_test_module_path,
    path_parts,
)
from .constants import (
    BOUNDARY_LOG_METHODS,
    BOUNDARY_LOG_NAMES,
    EVENT_CALL_NAMES,
    EVENT_NAME_MARKERS,
    EVENT_PATH_PARTS,
    HTTP_BOUNDARY_METHODS,
    PACKAGE_BOUNDARY_CLASS_SUFFIXES,
    PACKAGE_BOUNDARY_NAME_PARTS,
    PACKAGE_BOUNDARY_PATH_PARTS,
)
from .kinds import (
    BoundaryFunction,
    boundary_kind_for_function,
    class_name_has_package_boundary_signal,
    contains_package_boundary_call,
    iter_public_boundary_functions,
)
from .requirement import PythonBoundaryLoggingRule

__all__ = [
    "BOUNDARY_LOG_METHODS",
    "BOUNDARY_LOG_NAMES",
    "BoundaryFunction",
    "EVENT_CALL_NAMES",
    "EVENT_NAME_MARKERS",
    "EVENT_PATH_PARTS",
    "HTTP_BOUNDARY_METHODS",
    "PACKAGE_BOUNDARY_CLASS_SUFFIXES",
    "PACKAGE_BOUNDARY_NAME_PARTS",
    "PACKAGE_BOUNDARY_PATH_PARTS",
    "PythonBoundaryLoggingRule",
    "attribute_chain_parts",
    "boundary_kind_for_function",
    "called_name",
    "class_name_has_package_boundary_signal",
    "contains_event_boundary_call",
    "contains_package_boundary_call",
    "function_name_has_event_signal",
    "has_boundary_log_call",
    "is_test_module_path",
    "iter_public_boundary_functions",
    "path_parts",
]
