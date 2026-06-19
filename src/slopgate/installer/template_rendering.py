"""Template rendering helpers for installer-owned extension files."""

from __future__ import annotations

import json
from dataclasses import dataclass

from slopgate.installer._shared import base_invocation


@dataclass(frozen=True, slots=True)
class InvocationTemplateRenderer:
    """Render installer template placeholders with safely quoted argv lists."""

    placeholder: str
    missing_message: str

    def __call__(self, template_text: str, binary: str) -> str:
        if self.placeholder not in template_text:
            raise ValueError(self.missing_message)
        return template_text.replace(
            self.placeholder, json.dumps(base_invocation(binary))
        )
