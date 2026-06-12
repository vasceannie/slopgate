"""Newline-framed JSON protocol for the resident hook daemon."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Protocol

from slopgate._types import ObjectDict, object_dict, string_value

FRAME_DELIMITER = b"\n"
FRAME_ENCODING = "utf-8"
MAX_FRAME_BYTES = 1024 * 1024


class _FrameConnection(Protocol):
    def recv(self, size: int, /) -> bytes: ...


@dataclass(frozen=True, slots=True)
class DaemonRequest:
    payload: ObjectDict
    platform: str | None = None
    event: str | None = None
    metadata: ObjectDict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DaemonResponse:
    ok: bool
    output: ObjectDict = field(default_factory=dict)
    error: str | None = None
    stderr: str | None = None
    exit_code: int = 0


def encode_request(request: DaemonRequest) -> bytes:
    payload: ObjectDict = {
        "payload": request.payload,
        "metadata": request.metadata,
    }
    if request.platform is not None:
        payload["platform"] = request.platform
    if request.event is not None:
        payload["event"] = request.event
    return _encode_frame(payload)


def decode_request(frame: bytes) -> DaemonRequest:
    data = _decode_frame(frame)
    return DaemonRequest(
        payload=object_dict(data.get("payload")),
        platform=string_value(data.get("platform")),
        event=string_value(data.get("event")),
        metadata=object_dict(data.get("metadata")),
    )


def encode_response(response: DaemonResponse) -> bytes:
    payload: ObjectDict = {
        "exit_code": response.exit_code,
        "ok": response.ok,
        "output": response.output,
    }
    if response.error is not None:
        payload["error"] = response.error
    if response.stderr is not None:
        payload["stderr"] = response.stderr
    return _encode_frame(payload)


def decode_response(frame: bytes) -> DaemonResponse:
    data = _decode_frame(frame)
    ok = data.get("ok") is True
    return DaemonResponse(
        ok=ok,
        output=object_dict(data.get("output")),
        error=string_value(data.get("error")),
        stderr=string_value(data.get("stderr")),
        exit_code=_int_value(data.get("exit_code")),
    )


def _encode_frame(payload: ObjectDict) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return body.encode(FRAME_ENCODING) + FRAME_DELIMITER


def _decode_frame(frame: bytes) -> ObjectDict:
    raw = frame.rstrip(FRAME_DELIMITER).decode(FRAME_ENCODING)
    parsed = json.loads(raw)
    return object_dict(parsed)


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def read_frame(
    connection: _FrameConnection, *, empty_message: str, size_message: str
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_FRAME_BYTES:
            raise ValueError(size_message)
        if FRAME_DELIMITER in chunk:
            break
    frame = b"".join(chunks).split(FRAME_DELIMITER, maxsplit=1)[0]
    if not frame:
        raise ValueError(empty_message)
    return frame + FRAME_DELIMITER


__all__ = [
    "DaemonRequest",
    "DaemonResponse",
    "decode_request",
    "decode_response",
    "encode_request",
    "encode_response",
    "read_frame",
]
