#!/usr/bin/env python3
"""Build a standalone ForceDash HTML with slopgate trace data pre-baked.

Usage:
    python3 scripts/build-standalone.py [--logs-dir DIR] [--output PATH] [--ssh HOST]

If --ssh is given, JSONL files are fetched from the remote host via scp.
Otherwise, --logs-dir should point to a local directory containing the JSONL files.

Output: a modified index.html from dist/ with trace data inlined as
window.__SLOPGATE_DATA__ so the dashboard loads real data without file drops.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, TypeAlias, TypedDict, cast

Category: TypeAlias = Literal["events", "rules", "results", "subprocesses"]
JSONDict: TypeAlias = dict[str, object]


class SlopgateConfig(TypedDict):
    enabled_rules: dict[str, bool]
    regex_rules: list[JSONDict]
    skip_paths: list[str]

JSONL_FILES = ["events.jsonl", "rules.jsonl", "results.jsonl", "subprocess.jsonl", "async/subprocess.jsonl"]
DEFAULT_REMOTE_LOGS = "~/.config/slopgate/logs"
DEFAULT_LOOKBACK_HOURS = 24
MAX_RECORDS_PER_CATEGORY: dict[Category, int] = {
    "events": 6000,
    "rules": 6000,
    "results": 6000,
    "subprocesses": 2000,
}
TRACE_META_KEYS = (
    "platform_capability",
    "degraded_reason",
    "enforcement_mode",
    "resolved_repo_root",
)
DASHBOARD_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = DASHBOARD_DIR / "dist"
CANVAS_DEPLOY = Path.home() / ".openclaw" / "canvas" / "forcedash"


def _coerce_object_dict(value: object) -> JSONDict | None:
    if not isinstance(value, Mapping):
        return None
    result: JSONDict = {}
    for key, item in cast(Mapping[object, object], value).items():
        if isinstance(key, str):
            result[key] = item
    return result


def _coerce_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    result: list[JSONDict] = []
    for item in cast(list[object], value):
        record = _coerce_object_dict(item)
        if record is not None:
            result.append(record)
    return result


def _coerce_object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def _coerce_bool_dict(value: object) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, bool] = {}
    for key, item in cast(Mapping[object, object], value).items():
        if isinstance(key, str) and isinstance(item, bool):
            result[key] = item
    return result


def _coerce_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            result.append(item)
    return result


def classify(obj: Mapping[str, object]) -> Category | None:
    """Classify a parsed JSONL line into a trace category."""
    if "command" in obj and "returncode" in obj:
        return "subprocesses"
    if "findings" in obj and isinstance(obj.get("findings"), list):
        return "results"
    if "rule_id" in obj and "decision" in obj and "severity" in obj:
        return "rules"
    if "event_name" in obj and "session_id" in obj:
        return "events"
    return None


def trim_text(value: object, limit: int) -> str | None:
    """Return a bounded string payload for dashboard display."""
    if not isinstance(value, str):
        return None
    if len(value) <= limit:
        return value
    return value[:limit] + "…[trimmed]"


def string_list(value: object) -> list[str]:
    return _coerce_str_list(value)


def trace_metadata(obj: Mapping[str, object]) -> JSONDict:
    """Preserve small, non-payload trace context already emitted by the engine."""
    meta: JSONDict = {}
    for key in TRACE_META_KEYS:
        if key in obj:
            value = obj[key]
            if isinstance(value, str) or value is None:
                meta[key] = value
    return meta


def project_record(obj: Mapping[str, object]) -> JSONDict | None:
    """Keep only the fields ForceDash actually reads."""
    category = classify(obj)
    if category == "events":
        return {
            "timestamp": obj.get("timestamp", ""),
            "platform": obj.get("platform", "claude"),
            "event_name": obj.get("event_name", ""),
            "session_id": obj.get("session_id", ""),
            "tool_name": obj.get("tool_name", ""),
            "candidate_paths": string_list(obj.get("candidate_paths")),
            "languages": string_list(obj.get("languages")),
            **trace_metadata(obj),
        }
    if category == "rules":
        return {
            "timestamp": obj.get("timestamp", ""),
            "platform": obj.get("platform", "claude"),
            "event_name": obj.get("event_name", ""),
            "session_id": obj.get("session_id", ""),
            "tool_name": obj.get("tool_name", ""),
            "rule_id": obj.get("rule_id", ""),
            "severity": obj.get("severity", "LOW"),
            "decision": obj.get("decision"),
            "message": trim_text(obj.get("message"), 180),
            "additional_context": trim_text(obj.get("additional_context"), 180),
            "metadata": {},
            **trace_metadata(obj),
        }
    if category == "results":
        findings: list[JSONDict] = []
        for finding_value in _coerce_dict_list(obj.get("findings")):
            finding = _coerce_object_dict(finding_value)
            if finding is None:
                continue
            findings.append(
                {
                    "rule_id": finding.get("rule_id", ""),
                    "severity": finding.get("severity", "LOW"),
                    "decision": finding.get("decision"),
                    "message": trim_text(finding.get("message"), 180),
                    "additional_context": trim_text(finding.get("additional_context"), 180),
                    **trace_metadata(finding),
                }
            )
        return {
            "timestamp": obj.get("timestamp", ""),
            "platform": obj.get("platform", "claude"),
            "event_name": obj.get("event_name", ""),
            "session_id": obj.get("session_id", ""),
            "tool_name": obj.get("tool_name", ""),
            "findings": findings,
            "errors": [
                text
                for err in _coerce_object_list(obj.get("errors"))
                for text in [trim_text(err, 180)]
                if text is not None
            ],
            "output": None,
            "skipped": bool(obj.get("skipped", False)),
            "reason": trim_text(obj.get("reason"), 180),
            **trace_metadata(obj),
        }
    if category == "subprocesses":
        return {
            "timestamp": obj.get("timestamp", ""),
            "event_name": obj.get("event_name", ""),
            "session_id": obj.get("session_id", ""),
            "command": trim_text(obj.get("command"), 180) or "",
            "cwd": trim_text(obj.get("cwd"), 120) or "",
            "returncode": obj.get("returncode", 0),
            "stdout": trim_text(obj.get("stdout"), 120) or "",
            "stderr": trim_text(obj.get("stderr"), 180) or "",
            "duration_ms": obj.get("duration_ms", 0),
        }
    return None


def load_jsonl(path: Path) -> list[JSONDict]:
    """Parse a JSONL file, skipping malformed lines."""
    records: list[JSONDict] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload: object = json.loads(line)
            except json.JSONDecodeError:
                continue
            record = _coerce_object_dict(payload)
            if record is not None:
                records.append(record)
    return records


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_cutoff(logs_dir: Path, lookback_hours: int) -> datetime | None:
    latest: datetime | None = None
    for fname in JSONL_FILES:
        for record in load_jsonl(logs_dir / fname):
            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is None:
                continue
            if latest is None or timestamp > latest:
                latest = timestamp
    if latest is None:
        return None
    return latest - timedelta(hours=lookback_hours)


def fetch_logs_ssh(host: str, remote_dir: str, local_dir: Path) -> None:
    """SCP JSONL files from a remote host.

    Some slopgate installs do not emit subprocess traces yet, so missing
    optional files should not abort the whole dashboard publish.
    """
    for fname in JSONL_FILES:
        src = f"{host}:{remote_dir}/{fname}"
        dst = local_dir / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"  scp {src} -> {dst}")
        result = subprocess.run(["scp", "-q", src, str(dst)], check=False)
        if result.returncode != 0:
            print(f"    missing on remote, skipping: {fname}")


def build_vite() -> None:
    """Run the Vite production build."""
    print("Building dashboard with bun...")
    subprocess.run(["bun", "install", "--frozen-lockfile"], cwd=DASHBOARD_DIR, check=True)
    subprocess.run(["bun", "run", "build"], cwd=DASHBOARD_DIR, check=True)
    print(f"Build output: {DIST_DIR}")


DEFAULTS_JSON = Path(__file__).resolve().parent.parent.parent / "src" / "slopgate" / "resources" / "defaults.json"
# Fallback: look in installed copy on gateway
DEFAULTS_FALLBACK = Path.home() / "slopgate" / "src" / "slopgate" / "resources" / "defaults.json"
REMOTE_CONFIG_PATH = "~/.config/slopgate/config.json"


def load_slopgate_config(ssh_host: str) -> SlopgateConfig:
    """Build a merged rule registry from defaults.json + live user config."""
    # Load defaults
    defaults_path = DEFAULTS_JSON if DEFAULTS_JSON.exists() else DEFAULTS_FALLBACK
    if not defaults_path.exists():
        print("  WARNING: defaults.json not found, skipping config injection", file=sys.stderr)
        return {"enabled_rules": {}, "regex_rules": [], "skip_paths": []}
    with defaults_path.open(encoding="utf-8") as f:
        defaults_raw: object = json.load(f)
    defaults = _coerce_object_dict(defaults_raw) or {}

    # Fetch live user config from remote
    user_config: JSONDict = {}
    try:
        r = subprocess.run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=5",
                ssh_host,
                "python3 - <<'PY'\nfrom pathlib import Path\nprint((Path.home() / '.config' / 'slopgate' / 'config.json').read_text())\nPY",
            ],
            capture_output=True, text=True, timeout=8,
        )
        if r.returncode == 0:
            user_config = _coerce_object_dict(json.loads(r.stdout)) or {}
            print(f"  Fetched live config from {ssh_host}")
        else:
            print(f"  WARNING: could not fetch config from {ssh_host}: {r.stderr.strip()[:80]}", file=sys.stderr)
    except Exception as e:
        print(f"  WARNING: config fetch failed: {e}", file=sys.stderr)

    # Build merged enabled_rules: defaults first, user overrides on top
    default_enabled = _coerce_bool_dict(defaults.get("enabled_rules"))
    user_enabled = _coerce_bool_dict(user_config.get("enabled_rules"))
    merged_enabled = {**default_enabled, **user_enabled}

    # Build regex_rules: defaults list, with user exclusion overrides applied
    default_regex = _coerce_dict_list(defaults.get("regex_rules"))
    user_regex_map: dict[str, JSONDict] = {}
    for rule in _coerce_dict_list(user_config.get("regex_rules")):
        rule_id = rule.get("rule_id")
        if isinstance(rule_id, str):
            user_regex_map[rule_id] = rule
    merged_regex: list[JSONDict] = []
    for rule in default_regex:
        rid_obj = rule.get("rule_id", "")
        rid = rid_obj if isinstance(rid_obj, str) else ""
        if rid in user_regex_map:
            # Merge: keep defaults fields, overlay user exclusions
            merged = {
                **rule,
                **{
                    key: value
                    for key, value in user_regex_map[rid].items()
                    if key == "exclude_path_globs"
                },
            }
            merged_regex.append(merged)
        else:
            merged_regex.append(rule)

    return {
        "enabled_rules": merged_enabled,
        "regex_rules": merged_regex,
        "skip_paths": _coerce_str_list(user_config.get("skip_paths", defaults.get("skip_paths", []))),
    }


def inject_data(
    index_html: Path,
    trace_data: Mapping[Category, list[JSONDict]],
    slopgate_config: SlopgateConfig | None = None,
) -> str:
    """Inject trace data (and optionally rule config) as script tags into the built index.html."""
    html = index_html.read_text(encoding="utf-8")
    payload = json.dumps(trace_data, separators=(",", ":"))
    scripts = [f"<script>window.__SLOPGATE_DATA__={payload};</script>"]
    if slopgate_config:
        cfg_payload = json.dumps(slopgate_config, separators=(",", ":"))
        scripts.append(f"<script>window.__SLOPGATE_CONFIG__={cfg_payload};</script>")
    block = "\n".join(scripts)
    if "</head>" in html:
        html = html.replace("</head>", f"{block}\n</head>")
    else:
        html = block + "\n" + html
    return html


def deploy_to_canvas(html: str, assets_dir: Path) -> Path:
    """Copy built assets + patched index.html to the canvas directory."""
    import shutil

    CANVAS_DEPLOY.mkdir(parents=True, exist_ok=True)

    # Copy all dist assets
    if CANVAS_DEPLOY.exists():
        shutil.rmtree(CANVAS_DEPLOY)
    shutil.copytree(assets_dir, CANVAS_DEPLOY, dirs_exist_ok=True)

    # Overwrite index.html with data-injected version
    out = CANVAS_DEPLOY / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Deployed to {CANVAS_DEPLOY}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", help="Local directory with JSONL files")
    parser.add_argument("--ssh", default="little", help="SSH host to fetch logs from (default: little)")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_LOGS, help="Remote logs directory")
    parser.add_argument("--output", help="Output HTML path (default: deploy to canvas)")
    parser.add_argument("--skip-build", action="store_true", help="Skip Vite build (use existing dist/)")
    parser.add_argument("--no-deploy", action="store_true", help="Don't deploy to canvas dir")
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=f"Only publish the newest N hours of trace history (default: {DEFAULT_LOOKBACK_HOURS})",
    )
    args = parser.parse_args()

    # Step 1: Get JSONL files
    if args.logs_dir:
        logs_dir = Path(args.logs_dir)
    else:
        logs_dir = Path(tempfile.mkdtemp(prefix="forcedash-logs-"))
        print(f"Fetching logs from {args.ssh}:{args.remote_dir}")
        fetch_logs_ssh(args.ssh, args.remote_dir, logs_dir)

    # Step 2: Parse, bound, and classify
    trace_data: dict[Category, list[JSONDict]] = {
        "events": [],
        "rules": [],
        "results": [],
        "subprocesses": [],
    }
    cutoff = compute_cutoff(logs_dir, args.lookback_hours)
    if cutoff is not None:
        print(f"Publishing records since {cutoff.isoformat()} ({args.lookback_hours}h lookback)")

    for fname in JSONL_FILES:
        records = load_jsonl(logs_dir / fname)
        for rec in records:
            timestamp = parse_timestamp(rec.get("timestamp"))
            if cutoff is not None and timestamp is not None and timestamp < cutoff:
                continue
            projected = project_record(rec)
            if projected is None:
                continue
            category = classify(projected)
            if category:
                trace_data[category].append(projected)

    for category, limit in MAX_RECORDS_PER_CATEGORY.items():
        if len(trace_data[category]) > limit:
            trace_data[category] = trace_data[category][-limit:]

    total = sum(len(v) for v in trace_data.values())
    print(f"Loaded {total} published records: "
          f"{len(trace_data['events'])} events, "
          f"{len(trace_data['rules'])} rules, "
          f"{len(trace_data['results'])} results, "
          f"{len(trace_data['subprocesses'])} subprocesses")

    # Step 3: Build
    if not args.skip_build:
        build_vite()

    index_html = DIST_DIR / "index.html"
    if not index_html.exists():
        print(f"ERROR: {index_html} not found. Run build first.", file=sys.stderr)
        sys.exit(1)

    # Step 4: Load rule config
    print(f"Loading slopgate rule config from {args.ssh}...")
    slopgate_config = load_slopgate_config(args.ssh)
    if slopgate_config:
        n_enabled = sum(1 for v in slopgate_config["enabled_rules"].values() if v)
        n_regex = len(slopgate_config["regex_rules"])
        print(f"  Config: {len(slopgate_config['enabled_rules'])} enabled_rules ({n_enabled} ON), {n_regex} regex_rules")

    # Step 5: Inject data
    html = inject_data(index_html, trace_data, slopgate_config or None)
    print(f"Injected {len(json.dumps(trace_data, separators=(',', ':')))} bytes of trace data")

    # Step 5: Output
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Written to {out}")
    elif not args.no_deploy:
        deploy_to_canvas(html, DIST_DIR)
    else:
        out = DIST_DIR / "standalone.html"
        out.write_text(html, encoding="utf-8")
        print(f"Written to {out}")


if __name__ == "__main__":
    main()
