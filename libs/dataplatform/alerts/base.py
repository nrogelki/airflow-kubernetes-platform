"""Channel-agnostic pieces shared by every alert template.

``AlertInfo`` normalises the Airflow callback ``context`` into plain values,
and ``build_text`` renders the human message used by the chat channels
(Slack, Teams, Google Chat, generic webhooks). Standard library only.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

DEFAULT_BASE_URL = os.environ.get("AIRFLOW_BASE_URL", "http://localhost:8080")
DEFAULT_TIMEZONE = os.environ.get("ALERT_TIMEZONE", "UTC")
MAX_REASON_LENGTH = 1500

# event -> (emoji, title, hex colour)
EVENTS = {
    "failure": ("🔴", "Task failed", "B91C1C"),
    "retry": ("🟠", "Task up for retry", "D97706"),
    "success": ("🟢", "DAG run succeeded", "15803D"),
}


@dataclass(frozen=True)
class AlertInfo:
    event: str
    dag_id: str
    task_id: str
    run_id: str
    logical_date: str
    at: str
    try_number: str
    reason: str
    task_url: str
    dag_url: str

    def as_dict(self) -> dict:
        return asdict(self)


def _fmt(dt: datetime | None, tz_name: str) -> str:
    if dt is None:
        return "N/A"
    return f"{dt.astimezone(ZoneInfo(tz_name)):%Y-%m-%d %H:%M:%S} ({tz_name})"


def _truncate(text: str, limit: int = MAX_REASON_LENGTH) -> str:
    return text if len(text) <= limit else text[:limit] + " [...truncated]"


def build_alert_info(
    context: dict,
    event: str = "failure",
    base_url: str = DEFAULT_BASE_URL,
    tz_name: str = DEFAULT_TIMEZONE,
) -> AlertInfo:
    """Normalise an Airflow callback context (task- or DAG-level) into ``AlertInfo``."""
    if event not in EVENTS:
        raise ValueError(f"Unknown event '{event}'. Use one of {sorted(EVENTS)}")
    ti = context.get("task_instance") or context.get("ti")
    dag = context.get("dag")
    dag_run = context.get("dag_run")

    dag_id = getattr(ti, "dag_id", None) or getattr(dag, "dag_id", None) or "unknown"
    task_id = getattr(ti, "task_id", None) or "-"
    run_id = getattr(ti, "run_id", None) or getattr(dag_run, "run_id", None) or context.get("run_id") or "unknown"
    at = getattr(ti, "end_date", None) or getattr(dag_run, "end_date", None) or datetime.now(UTC)
    reason = context.get("exception") or context.get("reason") or ""

    base = base_url.rstrip("/")
    dag_link = f"{base}/dags/{quote(str(dag_id), safe='')}"
    task_link = f"{dag_link}/runs/{quote(str(run_id), safe='')}"
    if task_id != "-":
        task_link += f"/tasks/{quote(str(task_id), safe='')}"

    return AlertInfo(
        event=event,
        dag_id=str(dag_id),
        task_id=str(task_id),
        run_id=str(run_id),
        logical_date=_fmt(context.get("logical_date"), tz_name),
        at=_fmt(at, tz_name),
        try_number=str(getattr(ti, "try_number", "-") if ti else "-"),
        reason=_truncate(str(reason)),
        task_url=task_link,
        dag_url=dag_link,
    )


def build_text(info: AlertInfo) -> str:
    """Plain/markdown message shared by the chat channels."""
    emoji, title, _ = EVENTS[info.event]
    lines = [
        f"{emoji} *{title}*: `{info.dag_id}.{info.task_id}`",
        f"• Run: `{info.run_id}`",
        f"• Logical date: {info.logical_date}",
        f"• At: {info.at}  (attempt {info.try_number})",
    ]
    if info.reason:
        lines.append(f"• Reason: {info.reason}")
    lines.append(f"<{info.task_url}|Open in Airflow>")
    return "\n".join(lines)
