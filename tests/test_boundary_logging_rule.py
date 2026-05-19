from __future__ import annotations

from pathlib import Path

from vibeforcer.engine import evaluate_payload
from vibeforcer.models import EngineResult


def _enrolled_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src" / "orders").mkdir(parents=True)
    _ = (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
        encoding="utf-8",
    )
    return repo


def _write_payload(repo: Path, path: str, content: str) -> dict[str, object]:
    return {
        "session_id": "boundary-logging-test",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path, "content": content},
    }


def _rule_ids(result: EngineResult) -> set[str]:
    return {finding.rule_id for finding in result.findings}


def test_event_boundary_publish_requires_log(tmp_path: Path) -> None:
    repo = _enrolled_repo(tmp_path)
    result = evaluate_payload(
        _write_payload(
            repo,
            "src/orders/events.py",
            """
from orders.bus import EventBus


def publish_order_created(bus: EventBus, order_id: str, source: str | None = None) -> None:
    event = {"order_id": order_id, "source": source or "api"}
    bus.publish("order.created", event)
""".lstrip(),
        )
    )

    rule_ids = _rule_ids(result)
    output = str(result.output)
    assert "PY-LOG-002" in rule_ids, f"Expected boundary log rule, got {rule_ids}"
    assert result.output is not None, "Expected PY-LOG-002 to emit hook output"
    assert "event boundary" in output, f"Expected event-boundary guidance in {output}"
    assert "logger.info" in output, f"Expected logger.info recovery guidance in {output}"


def test_package_boundary_client_call_requires_log(tmp_path: Path) -> None:
    repo = _enrolled_repo(tmp_path)
    result = evaluate_payload(
        _write_payload(
            repo,
            "src/orders/clients/billing.py",
            """
class BillingClient:
    def charge_order(self, payload: dict[str, str]) -> dict[str, str]:
        request = {"metadata": {"source": "orders"}, **payload}
        response = self._http.post("/charges", json=request)
        return {"status": response.status_code, "body": response.text}
""".lstrip(),
        )
    )

    assert "PY-LOG-002" in _rule_ids(result)
    assert result.output is not None
    assert "package boundary" in str(result.output)


def test_logged_event_boundary_is_allowed(tmp_path: Path) -> None:
    repo = _enrolled_repo(tmp_path)
    result = evaluate_payload(
        _write_payload(
            repo,
            "src/orders/events.py",
            """
from orders.observability import logger
from orders.bus import EventBus


def publish_order_created(bus: EventBus, order_id: str) -> None:
    logger.info("publishing order event", extra={"event": "order.created", "order_id": order_id})
    bus.publish("order.created", {"order_id": order_id})
""".lstrip(),
        )
    )

    assert "PY-LOG-002" not in _rule_ids(result)


def test_internal_helper_without_boundary_signal_does_not_require_log(tmp_path: Path) -> None:
    repo = _enrolled_repo(tmp_path)
    result = evaluate_payload(
        _write_payload(
            repo,
            "src/orders/calculations.py",
            """
def total_cents(amounts: list[int]) -> int:
    total = 0
    for amount in amounts:
        total += amount
    return total
""".lstrip(),
        )
    )

    assert "PY-LOG-002" not in _rule_ids(result)
