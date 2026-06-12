from __future__ import annotations

import argparse
from collections.abc import Callable
import importlib
from typing import Protocol, cast

from hypothesis import given, strategies

JSON_SCALAR = strategies.one_of(
    strategies.none(),
    strategies.booleans(),
    strategies.integers(min_value=-100, max_value=100),
    strategies.text(alphabet="abcxyz0123 _.-", max_size=20),
)
JSON_OBJECTS = strategies.dictionaries(
    strategies.text(alphabet="abcxyz_", min_size=1, max_size=8),
    JSON_SCALAR,
    max_size=4,
)
SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _.-/", max_size=40
)


class _ObjectFactory(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


class _DaemonModule(Protocol):
    DaemonRequest: _ObjectFactory
    DaemonResponse: _ObjectFactory


class _DaemonProtocolModule(Protocol):
    decode_request: Callable[[bytes], object]
    decode_response: Callable[[bytes], object]
    encode_request: Callable[[object], bytes]
    encode_response: Callable[[object], bytes]

    def read_frame(
        self, connection: object, *, empty_message: str, size_message: str
    ) -> bytes: ...


class _HookRuntimeRegistrationFactory(Protocol):
    def __call__(
        self,
        *,
        add_command_parser: object,
        add_platform_argument: object,
        help_by_name: dict[str, str],
        func_by_name: dict[str, object],
    ) -> object: ...


class _HookRuntimeParsersModule(Protocol):
    HookRuntimeParserRegistration: _HookRuntimeRegistrationFactory

    def add_hook_runtime_parsers(
        self,
        sub: argparse._SubParsersAction[argparse.ArgumentParser],
        registration: object,
    ) -> None: ...


_daemon = cast(_DaemonModule, importlib.import_module("slopgate.daemon"))
_daemon_protocol = cast(
    _DaemonProtocolModule, importlib.import_module("slopgate.daemon.protocol")
)
_hook_runtime_parsers = cast(
    _HookRuntimeParsersModule,
    importlib.import_module("slopgate.cli.hook_runtime_parsers"),
)


class _ChunkedConnection:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def recv(self, _size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


def _add_command_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    *,
    help_text: str,
    func: object,
) -> argparse.ArgumentParser:
    command_parser = sub.add_parser(name, help=help_text)
    command_parser.set_defaults(func=func)
    return command_parser


def _add_platform_argument(command_parser: argparse.ArgumentParser) -> None:
    _ = command_parser.add_argument("--platform", default="codex")


def _parse_registered_daemon(max_requests: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    funcs = {
        "handle": object(),
        "daemon": object(),
        "handle-async": object(),
        "replay": object(),
    }
    registration = _hook_runtime_parsers.HookRuntimeParserRegistration(
        add_command_parser=_add_command_parser,
        add_platform_argument=_add_platform_argument,
        help_by_name={name: f"{name} help" for name in funcs},
        func_by_name=funcs,
    )
    _hook_runtime_parsers.add_hook_runtime_parsers(sub, registration)
    return parser.parse_args(
        [
            "daemon",
            "--socket",
            "/tmp/slopgate.sock",
            "--max-requests",
            str(max_requests),
        ]
    )


@given(
    payload=JSON_OBJECTS, metadata=JSON_OBJECTS, platform=SHORT_TEXT, event=SHORT_TEXT
)
def test_encode_request_round_trips_json_payload_property(
    payload: dict[str, object],
    metadata: dict[str, object],
    platform: str,
    event: str,
) -> None:
    request = _daemon.DaemonRequest(
        payload=payload,
        metadata=metadata,
        platform=platform or None,
        event=event or None,
    )

    decoded = _daemon_protocol.decode_request(_daemon_protocol.encode_request(request))

    assert decoded == request


@given(output=JSON_OBJECTS, exit_code=strategies.integers(min_value=-5, max_value=5))
def test_encode_response_round_trips_exit_contract_property(
    output: dict[str, object],
    exit_code: int,
) -> None:
    response = _daemon.DaemonResponse(
        ok=exit_code == 0,
        output=output,
        stderr="blocked\n" if exit_code else None,
        exit_code=exit_code,
    )

    decoded = _daemon_protocol.decode_response(
        _daemon_protocol.encode_response(response)
    )

    assert decoded == response


@given(
    frame=strategies.binary(min_size=1, max_size=64).filter(
        lambda data: b"\n" not in data
    )
)
def test_read_frame_returns_single_newline_terminated_frame_property(
    frame: bytes,
) -> None:
    connection = _ChunkedConnection([frame[:1], frame[1:] + b"\ntrailing"])

    observed = _daemon_protocol.read_frame(
        connection, empty_message="empty", size_message="oversized"
    )

    assert observed == frame + b"\n"


@given(max_requests=strategies.integers(min_value=0, max_value=3))
def test_add_hook_runtime_parsers_registers_daemon_options_property(
    max_requests: int,
) -> None:
    args = _parse_registered_daemon(max_requests)

    assert {"command": args.command, "max_requests": args.max_requests} == {
        "command": "daemon",
        "max_requests": max_requests,
    }
