"""Chat / webhook alert templates for Airflow callbacks.

Ready-to-use callback factories:

=====================  ==========================================  ==================
Factory                Channel                                     Payload
=====================  ==========================================  ==================
slack_alert            Slack Incoming Webhook                      Block Kit
teams_alert            Microsoft Teams (Workflows webhook)         Adaptive Card
google_chat_alert      Google Chat space webhook                   text
webhook_alert          Any HTTP endpoint (PagerDuty proxy, n8n…)   AlertInfo as JSON
=====================  ==========================================  ==================

Every factory takes ``conn_id`` (the webhook URL NEVER goes in code) and
``event`` = ``"failure"`` | ``"retry"`` | ``"success"``::

    from dataplatform.alerts.webhooks import slack_alert, teams_alert

    default_args = {
        "on_failure_callback": [slack_alert("slack_alerts"), teams_alert("teams_alerts")],
        "on_retry_callback": [slack_alert("slack_alerts", event="retry")],
    }

    @dag(..., on_success_callback=[slack_alert("slack_alerts", event="success")])

Connection setup (Admin -> Connections): type **HTTP**, paste the full webhook
URL in the **Password** field (it is stored encrypted and masked in logs).
``host`` and the extra ``{"webhook_url": ...}`` are accepted as fallbacks.

Callbacks never raise: a broken webhook must not hide the task failure.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable

from dataplatform.alerts.base import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEZONE,
    EVENTS,
    AlertInfo,
    build_alert_info,
    build_text,
)

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10


# -- Payload builders (pure functions, unit-tested) -------------------------------


def slack_payload(info: AlertInfo) -> dict:
    emoji, title, colour = EVENTS[info.event]
    fields = [
        {"type": "mrkdwn", "text": f"*DAG*\n`{info.dag_id}`"},
        {"type": "mrkdwn", "text": f"*Task*\n`{info.task_id}`"},
        {"type": "mrkdwn", "text": f"*Logical date*\n{info.logical_date}"},
        {"type": "mrkdwn", "text": f"*At*\n{info.at}"},
    ]
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} {title}"}},
        {"type": "section", "fields": fields},
    ]
    if info.reason:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Reason*\n```{info.reason}```"}})
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Open in Airflow"}, "url": info.task_url}
            ],
        }
    )
    # `text` is the notification fallback; the attachment gives the coloured bar.
    return {
        "text": f"{emoji} {title}: {info.dag_id}.{info.task_id}",
        "attachments": [{"color": f"#{colour}", "blocks": blocks}],
    }


def teams_payload(info: AlertInfo) -> dict:
    emoji, title, _ = EVENTS[info.event]
    facts = [
        {"title": "DAG", "value": info.dag_id},
        {"title": "Task", "value": info.task_id},
        {"title": "Run", "value": info.run_id},
        {"title": "Logical date", "value": info.logical_date},
        {"title": "At", "value": f"{info.at} (attempt {info.try_number})"},
    ]
    body: list[dict] = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "text": f"{emoji} {title}",
            "color": "Attention" if info.event == "failure" else "Default",
        },
        {"type": "FactSet", "facts": facts},
    ]
    if info.reason:
        body.append({"type": "TextBlock", "text": info.reason, "wrap": True, "fontType": "Monospace"})
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": [{"type": "Action.OpenUrl", "title": "Open in Airflow", "url": info.task_url}],
    }
    return {
        "type": "message",
        "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
    }


def google_chat_payload(info: AlertInfo) -> dict:
    # Google Chat uses <url|text> links, same syntax as build_text.
    return {"text": build_text(info)}


def generic_payload(info: AlertInfo) -> dict:
    return {"source": "airflow", **info.as_dict()}


# -- Delivery -------------------------------------------------------------------------


def resolve_webhook_url(conn_id: str) -> str:
    """Webhook URL from an Airflow Connection: password > extra.webhook_url > host."""
    from airflow.sdk import BaseHook

    conn = BaseHook.get_connection(conn_id)
    url = conn.password or conn.extra_dejson.get("webhook_url") or conn.host or ""
    if not url.startswith("http"):
        raise ValueError(f"Connection '{conn_id}' has no webhook URL (put it in the Password field)")
    return url


def post_json(url: str, payload: dict, timeout: int = TIMEOUT_SECONDS) -> int:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL comes from a Connection
        return resp.status


def _make_callback(
    builder: Callable[[AlertInfo], dict],
    channel: str,
    conn_id: str,
    event: str,
    base_url: str,
    tz_name: str,
) -> Callable[[dict], None]:
    if event not in EVENTS:
        raise ValueError(f"Unknown event '{event}'. Use one of {sorted(EVENTS)}")

    def _callback(context: dict) -> None:
        try:
            info = build_alert_info(context, event=event, base_url=base_url, tz_name=tz_name)
            status = post_json(resolve_webhook_url(conn_id), builder(info))
            log.info("%s %s alert sent via '%s' (HTTP %s)", channel, event, conn_id, status)
        except Exception:  # noqa: BLE001 — alerting must never mask the task outcome
            log.exception("Could not send %s %s alert via '%s'", channel, event, conn_id)

    _callback.__name__ = f"{channel}_{event}_alert"
    return _callback


def slack_alert(conn_id: str = "slack_alerts", event: str = "failure", base_url: str = DEFAULT_BASE_URL,
                tz_name: str = DEFAULT_TIMEZONE):  # fmt: skip
    """Slack Incoming Webhook callback."""
    return _make_callback(slack_payload, "slack", conn_id, event, base_url, tz_name)


def teams_alert(conn_id: str = "teams_alerts", event: str = "failure", base_url: str = DEFAULT_BASE_URL,
                tz_name: str = DEFAULT_TIMEZONE):  # fmt: skip
    """Microsoft Teams (Power Automate "Workflows" webhook) callback."""
    return _make_callback(teams_payload, "teams", conn_id, event, base_url, tz_name)


def google_chat_alert(conn_id: str = "google_chat_alerts", event: str = "failure",
                      base_url: str = DEFAULT_BASE_URL, tz_name: str = DEFAULT_TIMEZONE):  # fmt: skip
    """Google Chat space webhook callback."""
    return _make_callback(google_chat_payload, "google_chat", conn_id, event, base_url, tz_name)


def webhook_alert(conn_id: str, event: str = "failure", base_url: str = DEFAULT_BASE_URL,
                  tz_name: str = DEFAULT_TIMEZONE):  # fmt: skip
    """Generic JSON webhook callback (the body is ``AlertInfo`` + ``source``)."""
    return _make_callback(generic_payload, "webhook", conn_id, event, base_url, tz_name)
