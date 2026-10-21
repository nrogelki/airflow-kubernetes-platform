from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from dataplatform.alerts import base, webhooks

TI = SimpleNamespace(
    dag_id="sales",
    task_id="load",
    run_id="scheduled__2026-01-15",
    end_date=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
    try_number=2,
)
CTX = {"task_instance": TI, "exception": ValueError("boom"), "logical_date": datetime(2026, 1, 15, tzinfo=UTC)}


def info(event="failure"):
    return base.build_alert_info(CTX, event=event, base_url="http://h:31399/", tz_name="UTC")


def test_alert_info_fields():
    i = info()
    assert i.dag_id == "sales" and i.task_id == "load" and i.try_number == "2"
    assert i.task_url == "http://h:31399/dags/sales/runs/scheduled__2026-01-15/tasks/load"
    assert i.reason == "boom"


def test_dag_level_context_has_no_task():
    ctx = {"dag": SimpleNamespace(dag_id="d"), "dag_run": SimpleNamespace(run_id="r", end_date=None)}
    i = base.build_alert_info(ctx, event="success", base_url="http://h")
    assert i.task_id == "-" and i.task_url == "http://h/dags/d/runs/r"


def test_unknown_event_rejected():
    with pytest.raises(ValueError):
        webhooks.slack_alert("x", event="exploded")


@pytest.mark.parametrize(
    "builder", [webhooks.slack_payload, webhooks.teams_payload, webhooks.google_chat_payload, webhooks.generic_payload]
)
def test_payloads_contain_dag_and_link(builder):
    import json

    text = json.dumps(builder(info()), ensure_ascii=False)
    assert "sales" in text and "http://h:31399/dags/sales" in text


def test_teams_is_adaptive_card():
    card = webhooks.teams_payload(info())["attachments"][0]
    assert card["contentType"] == "application/vnd.microsoft.card.adaptive"


def test_callback_posts_and_never_raises(monkeypatch):
    sent = {}
    monkeypatch.setattr(webhooks, "resolve_webhook_url", lambda conn_id: "https://example/hook")
    monkeypatch.setattr(webhooks, "post_json", lambda url, payload: sent.update(url=url, payload=payload) or 200)
    webhooks.slack_alert("slack_alerts")(CTX)
    assert sent["url"] == "https://example/hook"

    def boom(url, payload):
        raise OSError("network down")

    monkeypatch.setattr(webhooks, "post_json", boom)
    webhooks.teams_alert("teams_alerts")(CTX)  # must not raise
