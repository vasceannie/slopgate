from __future__ import annotations

from typing import final

from vibeforcer._types import ObjectMapping, object_dict
from vibeforcer.models import RuntimeConfig

from ._properties import HookPayloadProperties


@final
class HookPayload(HookPayloadProperties):
    def __init__(self, payload: ObjectMapping, config: RuntimeConfig) -> None:
        self.payload = object_dict(payload)
        self.config = config
