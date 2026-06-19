from __future__ import annotations

import json

import pytest

from slopgate.installer._shared import base_invocation
from slopgate.installer.template_rendering import InvocationTemplateRenderer

_PLACEHOLDER = '["__SLOPGATE_BIN__"]'
_MISSING_MESSAGE = "template is missing the slopgate binary placeholder"


def test_invocation_template_renderer_uses_shared_invocation() -> None:
    renderer = InvocationTemplateRenderer(_PLACEHOLDER, _MISSING_MESSAGE)
    rendered = renderer(f"prefix {_PLACEHOLDER} suffix", "/tmp/slopgate")
    expected = f"prefix {json.dumps(base_invocation('/tmp/slopgate'))} suffix"
    assert rendered == expected, (
        "InvocationTemplateRenderer should use shared argv semantics"
    )


def test_invocation_template_renderer_reports_missing_placeholder() -> None:
    renderer = InvocationTemplateRenderer(_PLACEHOLDER, _MISSING_MESSAGE)
    with pytest.raises(ValueError, match=_MISSING_MESSAGE):
        renderer("template without placeholder", "/tmp/slopgate")
