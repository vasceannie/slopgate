#!/usr/bin/env python3
"""Find code-smell evidence that should trigger utility reuse/consolidation."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from _code_smell_scan import FunctionRecord, scan


DEFAULT_SMELL_KINDS = (
    "thin-wrapper",
    "feature-envy",
    "duplicate-body",
    "duplicate-signature",
    "repeated-helper-name",
)
UTILITY_NAME_TOKENS = (
    "helper",
    "util",
    "build",
    "make",
    "create",
    "factory",
    "config",
)
MAX_LOCATION_PREVIEW = 6


@dataclass(frozen=True)
class Smell:
    kind: str
    path: str
    line: int
    signature: str
    evidence: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository root or subdirectory to scan",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--limit", type=int, default=160, help="Maximum smell records to print"
    )
    parser.add_argument(
        "--no-tests", action="store_true", help="Skip tests/spec directories"
    )
    parser.add_argument(
        "--min-duplicate-size",
        type=int,
        default=3,
        help="Minimum normalized statements for duplicate body reporting",
    )
    parser.add_argument("--kind", action="append", choices=DEFAULT_SMELL_KINDS)
    return parser.parse_args(argv)


def _preview_locations(group: list[FunctionRecord]) -> str:
    locations = ", ".join(
        f"{func.path}:{func.line}" for func in group[:MAX_LOCATION_PREVIEW]
    )
    if len(group) > MAX_LOCATION_PREVIEW:
        return f"{locations}, ..."
    return locations


def _thin_wrapper_smell(func: FunctionRecord) -> Smell | None:
    if not func.is_thin_wrapper or not func.wrapper_target:
        return None
    return Smell(
        "thin-wrapper",
        func.path,
        func.line,
        func.signature,
        f"single delegating call to {func.wrapper_target}",
    )


def _feature_envy_smell(func: FunctionRecord) -> Smell | None:
    if not func.feature_envy_target:
        return None
    evidence = (
        f"{func.feature_envy_ratio:.0%} attribute accesses target parameter "
        f"`{func.feature_envy_target}`"
    )
    return Smell("feature-envy", func.path, func.line, func.signature, evidence)


def _single_function_smells(funcs: list[FunctionRecord]) -> list[Smell]:
    smells: list[Smell] = []
    for func in funcs:
        for smell in (_thin_wrapper_smell(func), _feature_envy_smell(func)):
            if smell is not None:
                smells.append(smell)
    return smells


def _duplicate_body_smells(
    funcs: list[FunctionRecord],
    min_duplicate_size: int,
) -> list[Smell]:
    by_body: dict[str, list[FunctionRecord]] = defaultdict(list)
    for func in funcs:
        if func.body_size >= min_duplicate_size:
            by_body[func.body_hash].append(func)

    smells: list[Smell] = []
    for group in by_body.values():
        if len(group) < 2:
            continue
        first = group[0]
        evidence = (
            f"same normalized body in {len(group)} functions: "
            f"{_preview_locations(group)}"
        )
        smells.append(
            Smell("duplicate-body", first.path, first.line, first.signature, evidence)
        )
    return smells


def _signature_tail(func: FunctionRecord) -> str:
    return f"{func.name}({func.signature.split('(', 1)[-1]}"


def _duplicate_signature_smells(funcs: list[FunctionRecord]) -> list[Smell]:
    by_sig_tail: dict[str, list[FunctionRecord]] = defaultdict(list)
    for func in funcs:
        by_sig_tail[_signature_tail(func)].append(func)

    smells: list[Smell] = []
    for group in by_sig_tail.values():
        paths = {func.path for func in group}
        if len(group) < 2 or len(paths) < 2 or group[0].name in {"main", "parse_args"}:
            continue
        first = group[0]
        evidence = (
            f"same function name/signature shape across {len(paths)} files: "
            f"{_preview_locations(group)}"
        )
        smells.append(
            Smell(
                "duplicate-signature", first.path, first.line, first.signature, evidence
            )
        )
    return smells


def _is_utility_like_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in UTILITY_NAME_TOKENS)


def _repeated_helper_name_smells(funcs: list[FunctionRecord]) -> list[Smell]:
    by_name: dict[str, list[FunctionRecord]] = defaultdict(list)
    for func in funcs:
        if _is_utility_like_name(func.name):
            by_name[func.name].append(func)

    smells: list[Smell] = []
    for name, group in by_name.items():
        paths = {func.path for func in group}
        if len(paths) < 3:
            continue
        first = group[0]
        evidence = (
            f"utility-like name `{name}` appears in {len(paths)} files: "
            f"{_preview_locations(group)}"
        )
        smells.append(
            Smell(
                "repeated-helper-name",
                first.path,
                first.line,
                first.signature,
                evidence,
            )
        )
    return smells


def smells_from_functions(
    funcs: list[FunctionRecord], min_duplicate_size: int
) -> list[Smell]:
    smells = [
        *_single_function_smells(funcs),
        *_duplicate_body_smells(funcs, min_duplicate_size),
        *_duplicate_signature_smells(funcs),
        *_repeated_helper_name_smells(funcs),
    ]
    smells.sort(key=lambda smell: (smell.kind, smell.path, smell.line, smell.signature))
    return smells


def print_text(smells: list[Smell], total_before_limit: int) -> None:
    print(f"code smell radar: showing {len(smells)} of {total_before_limit} matches")
    current = ""
    for smell in smells:
        if smell.kind != current:
            current = smell.kind
            print(f"\n[{current}]")
        print(f"- {smell.path}:{smell.line} {smell.signature}")
        print(f"  evidence: {smell.evidence}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        print(f"error: root does not exist: {root}", file=sys.stderr)
        return 2
    _items, funcs = scan(root, include_tests=not args.no_tests)
    smells = smells_from_functions(funcs, args.min_duplicate_size)
    if args.kind:
        kinds = set(args.kind)
        smells = [smell for smell in smells if smell.kind in kinds]
    total = len(smells)
    limited = smells[: max(args.limit, 0)]
    if args.format == "json":
        print(
            json.dumps([asdict(smell) for smell in limited], indent=2, sort_keys=True)
        )
    else:
        print_text(limited, total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
