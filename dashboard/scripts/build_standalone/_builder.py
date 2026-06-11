from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path

from .coercion import (
    coerce_bool_dict,
    coerce_dict_list,
    coerce_object_dict,
    coerce_str_list,
)
from .projection import (
    Category,
    JSONDict,
    SlopgateConfig,
    JSONL_FILES,
    DEFAULT_REMOTE_LOGS,
    DEFAULT_LOOKBACK_HOURS,
    MAX_RECORDS_PER_CATEGORY,
    DASHBOARD_DIR,
    DIST_DIR,
    CANVAS_DEPLOY,
    classify,
    format_item,
)


def _load_jsonl(path: Path) -> list[JSONDict]:
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
            record = coerce_object_dict(payload)
            if record is not None:
                records.append(record)
    return records


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compute_cutoff(logs_dir: Path, lookback_hours: int) -> datetime | None:
    latest: datetime | None = None
    for fname in JSONL_FILES:
        for record in _load_jsonl(logs_dir / fname):
            timestamp = _parse_timestamp(record.get("timestamp"))
            if timestamp is None:
                continue
            if latest is None or timestamp > latest:
                latest = timestamp
    if latest is None:
        return None
    return latest - timedelta(hours=lookback_hours)


def _fetch_logs_ssh(host: str, remote_dir: str, local_dir: Path) -> None:
    """SCP JSONL files from a remote host."""
    for fname in JSONL_FILES:
        src = f"{host}:{remote_dir}/{fname}"
        dst = local_dir / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"  scp {src} -> {dst}")
        result = subprocess.run(["scp", "-q", src, str(dst)], check=False)
        if result.returncode != 0:
            print(f"    missing on remote, skipping: {fname}")


def _build_vite() -> None:
    """Run the Vite production build."""
    print("Building dashboard with bun...")
    subprocess.run(["bun", "install", "--frozen-lockfile"], cwd=DASHBOARD_DIR, check=True)
    subprocess.run(["bun", "run", "build"], cwd=DASHBOARD_DIR, check=True)
    print(f"Build output: {DIST_DIR}")


DEFAULTS_JSON = DASHBOARD_DIR.parent / "src" / "slopgate" / "resources" / "defaults.json"
DEFAULTS_FALLBACK = Path.home() / "slopgate" / "src" / "slopgate" / "resources" / "defaults.json"
REMOTE_CONFIG_PATH = "~/.config/slopgate/config.json"


def _fetch_remote_user_config(ssh_host: str) -> JSONDict:
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
            res = coerce_object_dict(json.loads(r.stdout))
            if res is not None:
                print(f"  Fetched live config from {ssh_host}")
                return res
        print(f"  WARNING: could not fetch config from {ssh_host}: {r.stderr.strip()[:80]}", file=sys.stderr)
    except Exception as e:
        print(f"  WARNING: config fetch failed: {e}", file=sys.stderr)
    return {}


def _merge_regex_rules(defaults: JSONDict, user_config: JSONDict) -> list[JSONDict]:
    default_regex = coerce_dict_list(defaults.get("regex_rules"))
    user_regex_map: dict[str, JSONDict] = {}
    for rule in coerce_dict_list(user_config.get("regex_rules")):
        rule_id = rule.get("rule_id")
        if isinstance(rule_id, str):
            user_regex_map[rule_id] = rule
    merged_regex: list[JSONDict] = []
    for rule in default_regex:
        rid_obj = rule.get("rule_id", "")
        rid = rid_obj if isinstance(rid_obj, str) else ""
        if rid in user_regex_map:
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
    return merged_regex


def _load_slopgate_config(ssh_host: str) -> SlopgateConfig:
    """Build a merged rule registry from defaults.json + live user config."""
    defaults_path = DEFAULTS_JSON if DEFAULTS_JSON.exists() else DEFAULTS_FALLBACK
    if not defaults_path.exists():
        print("  WARNING: defaults.json not found, skipping config injection", file=sys.stderr)
        return {"enabled_rules": {}, "regex_rules": [], "skip_paths": []}
    with defaults_path.open(encoding="utf-8") as f:
        defaults_raw: object = json.load(f)
    defaults = coerce_object_dict(defaults_raw) or {}

    user_config = _fetch_remote_user_config(ssh_host)

    default_enabled = coerce_bool_dict(defaults.get("enabled_rules"))
    user_enabled = coerce_bool_dict(user_config.get("enabled_rules"))
    merged_enabled = {**default_enabled, **user_enabled}

    merged_regex = _merge_regex_rules(defaults, user_config)

    return {
        "enabled_rules": merged_enabled,
        "regex_rules": merged_regex,
        "skip_paths": coerce_str_list(user_config.get("skip_paths", defaults.get("skip_paths", []))),
    }


def _inject_data(
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


def _deploy_to_canvas(html: str, assets_dir: Path) -> Path:
    """Copy built assets + patched index.html to the canvas directory."""
    import shutil

    CANVAS_DEPLOY.mkdir(parents=True, exist_ok=True)

    if CANVAS_DEPLOY.exists():
        shutil.rmtree(CANVAS_DEPLOY)
    shutil.copytree(assets_dir, CANVAS_DEPLOY, dirs_exist_ok=True)

    out = CANVAS_DEPLOY / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Deployed to {CANVAS_DEPLOY}")
    return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ForceDash standalone HTML")
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
        help="Only publish the newest N hours of trace history",
    )
    return parser.parse_args()


def _prepare_logs_dir(args: argparse.Namespace) -> Path:
    if args.logs_dir:
        return Path(args.logs_dir)
    logs_dir = Path(tempfile.mkdtemp(prefix="forcedash-logs-"))
    print(f"Fetching logs from {args.ssh}:{args.remote_dir}")
    _fetch_logs_ssh(args.ssh, args.remote_dir, logs_dir)
    return logs_dir


def _collect_trace_records(
    logs_dir: Path,
    lookback_hours: int,
) -> dict[Category, list[JSONDict]]:
    trace_data: dict[Category, list[JSONDict]] = {
        "events": [],
        "rules": [],
        "results": [],
        "subprocesses": [],
    }
    cutoff = _compute_cutoff(logs_dir, lookback_hours)
    if cutoff is not None:
        print(f"Publishing records since {cutoff.isoformat()} ({lookback_hours}h lookback)")

    for fname in JSONL_FILES:
        records = _load_jsonl(logs_dir / fname)
        for rec in records:
            timestamp = _parse_timestamp(rec.get("timestamp"))
            if cutoff is not None and timestamp is not None and timestamp < cutoff:
                continue
            projected = format_item(rec)
            if projected is None:
                continue
            category = classify(projected)
            if category:
                trace_data[category].append(projected)

    for category, limit in MAX_RECORDS_PER_CATEGORY.items():
        if len(trace_data[category]) > limit:
            trace_data[category] = trace_data[category][-limit:]
    return trace_data


def _write_standalone_html(
    trace_data: dict[Category, list[JSONDict]],
    args: argparse.Namespace,
) -> None:
    if not args.skip_build:
        _build_vite()

    index_html = DIST_DIR / "index.html"
    if not index_html.exists():
        print(f"ERROR: {index_html} not found. Run build first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading slopgate rule config from {args.ssh}...")
    slopgate_config = _load_slopgate_config(args.ssh)
    if slopgate_config:
        n_enabled = sum(1 for v in slopgate_config["enabled_rules"].values() if v)
        n_regex = len(slopgate_config["regex_rules"])
        print(f"  Config: {len(slopgate_config['enabled_rules'])} enabled_rules ({n_enabled} ON), {n_regex} regex_rules")

    html = _inject_data(index_html, trace_data, slopgate_config or None)
    print(f"Injected {len(json.dumps(trace_data, separators=(',', ':')))} bytes of trace data")

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Written to {out}")
    elif not args.no_deploy:
        _deploy_to_canvas(html, DIST_DIR)
    else:
        out = DIST_DIR / "standalone.html"
        out.write_text(html, encoding="utf-8")
        print(f"Written to {out}")


def main() -> None:
    args = _parse_args()
    logs_dir = _prepare_logs_dir(args)
    trace_data = _collect_trace_records(logs_dir, args.lookback_hours)

    total = sum(len(v) for v in trace_data.values())
    print(f"Loaded {total} published records: "
          f"{len(trace_data['events'])} events, "
          f"{len(trace_data['rules'])} rules, "
          f"{len(trace_data['results'])} results, "
          f"{len(trace_data['subprocesses'])} subprocesses")

    _write_standalone_html(trace_data, args)
