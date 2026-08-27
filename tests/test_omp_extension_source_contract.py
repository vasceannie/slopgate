from __future__ import annotations

import json
from pathlib import Path

from slopgate.resources import resource_path


RUNTIME_DIR = Path(__file__).parent / "runtime" / "omp"
TYPECHECK_COMMAND = (
    "tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler "
    "--strict --skipLibCheck --types node --verbatimModuleSyntax staged/omp_extension.ts"
)


def omp_extension_source() -> str:
    path = resource_path("omp_extension.ts")
    assert path.is_file(), "Todo 4 must provide the OMP extension bridge template"
    return path.read_text(encoding="utf-8")


def test_omp_extension_contains_required_bridge_contract() -> None:
    source = omp_extension_source()
    required = (
        "OMP Slopgate Extension",
        'import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent"',
        'from "@oh-my-pi/pi-tui"',
        "export default function slopgateOmpExtension(pi: ExtensionAPI)",
        'pi.registerMessageRenderer("slopgate-event"',
        'pi.registerCommand("slopgate-context"',
        'pi.on("session_start"',
        'pi.on("before_agent_start"',
        'pi.on("input"',
        'pi.on("tool_call"',
        'pi.on("tool_result"',
        'pi.on("session_stop"',
        'pi.on("turn_end"',
        'pi.on("agent_end"',
        'pi.on("user_bash"',
        'pi.on("user_python"',
        "extractSessionStopResponse(event.last_assistant_message)",
        "stop_response: stopResponse || undefined",
        '"handle", "--platform", "omp"',
        "findManagedRepoRoot",
        "__SLOPGATE_BIN__",
        "SLOPGATE_OMP_INPUT_REWRITE",
        "SLOPGATE_SESSION_ID",
        "stop_hook_active",
        "advisory",
    )
    missing = [marker for marker in required if marker not in source]
    assert not missing, f"OMP bridge contract is missing markers: {missing!r}"


def test_omp_extension_excludes_unsafe_or_foreign_protocols() -> None:
    source = omp_extension_source()
    forbidden = (
        "@earendil-works",
        "@ts-ignore",
        "@ts-expect-error",
        "require(",
        "Buffer",
        'pi.on("tool_execution_',
        "Object.assign(event.input",
        'action: "handled"',
        'action: "transform"',
    )
    present = [marker for marker in forbidden if marker in source]
    assert not present, f"OMP bridge contains forbidden markers: {present!r}"


def test_omp_extension_declares_every_stop_counter_reset_site() -> None:
    source = omp_extension_source()
    assert "stopContinuationCounts.clear()" in source, (
        "session_start must prune all stored stop-continuation counters"
    )
    assert source.count("resetStopContinuationCount(sessionId)") == 5, (
        "input plus clean, stop-hook, cap-exhaustion, and advisory settles must reset the session counter"
    )


def test_omp_extension_placeholder_substitution_smoke() -> None:
    source = omp_extension_source()
    invocation = ["/tmp/slopgate-python", "-m", "slopgate"]
    rendered = source.replace('["__SLOPGATE_BIN__"]', json.dumps(invocation))
    assert "__SLOPGATE_BIN__" not in rendered, "renderer must replace the argv placeholder"
    assert json.dumps(invocation) in rendered, "renderer must preserve the complete invocation argv"


def test_omp_runtime_compile_command_is_exact() -> None:
    package = json.loads((RUNTIME_DIR / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["typecheck"] == TYPECHECK_COMMAND, (
        "Todo 4 owns the exact config-free raw-copy typecheck command"
    )
    assert not (RUNTIME_DIR / "tsconfig.json").exists(), (
        "OMP compile checks must remain config-free because protected-path hooks reject that filename"
    )
