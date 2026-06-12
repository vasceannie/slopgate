#!/usr/bin/env python3
"""Parse `slopgate lint check --details` stdout into structured JSON.

Usage:
    slopgate lint check --details 2>&1 | python3 parse_slopgate_lint.py --output slopgate_lint.json
    python3 parse_slopgate_lint.py --input lint_output.txt --output slopgate_lint.json
"""

import argparse
import json
import re
import sys


def parse_slopgate_lint(text: str) -> dict:
    """Parse slopgate lint check --details output into structured JSON."""
    lines = text.splitlines()

    # Parse header (first 10 lines)
    header = {}
    for line in lines[:10]:
        if line.startswith("  project:"):
            header["project"] = line.split(":", 1)[1].strip()
        elif line.startswith("  baseline:"):
            header["baseline"] = line.split(":", 1)[1].strip()
        elif line.startswith("  src:"):
            header["src"] = line.split(":", 1)[1].strip()
        elif line.startswith("  tests:"):
            header["tests"] = line.split(":", 1)[1].strip()

    # Parse collector summary lines
    collectors = []
    for m in re.finditer(r"^\s*✓\s+(\S+)\s+(\d+)\s+total", text, re.MULTILINE):
        collectors.append({"name": m.group(1), "total": int(m.group(2)), "new": 0})
    for m in re.finditer(
        r"^\s*✗\s+(\S+)\s+(\d+)\s+total,\s+(\d+)\s+NEW", text, re.MULTILINE
    ):
        collectors.append(
            {"name": m.group(1), "total": int(m.group(2)), "new": int(m.group(3))}
        )

    # Parse individual findings
    findings = []
    blocks = re.split(r"\n(?=    \[(NEW|BASELINE|FIXED)\])", text)
    for block in blocks:
        if not block.strip():
            continue
        block_lines = block.splitlines()
        status_match = re.match(
            r"^\s*\[(NEW|BASELINE|FIXED)\]\s+(\S+)",
            block_lines[0] if block_lines else "",
        )
        if not status_match:
            continue
        status = status_match.group(1)
        collector = status_match.group(2)
        finding = {"status": status, "collector": collector, "fields": {}}
        for line in block_lines[1:]:
            if line.startswith("    "):
                m = re.match(r"^    ([\w.\-]+):\s*(.*)", line)
                if m:
                    key, val = m.group(1), m.group(2)
                    finding["fields"][key] = val
        findings.append(finding)

    return {
        "header": header,
        "summary": {
            "collectors": collectors,
            "total_findings": len(findings),
            "new_findings": len([f for f in findings if f["status"] == "NEW"]),
            "baseline_findings": len(
                [f for f in findings if f["status"] == "BASELINE"]
            ),
            "fixed_findings": len([f for f in findings if f["status"] == "FIXED"]),
        },
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse slopgate lint check --details output"
    )
    parser.add_argument("--input", "-i", help="Input file (default: stdin)")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = parse_slopgate_lint(text)

    output_json = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
