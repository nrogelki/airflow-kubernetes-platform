"""HTML email alert for Airflow ``on_failure_callback``.

Any DAG wires it through ``default_args``::

    from dataplatform.alerts.email_alerts import task_failure_email_alert

    default_args = {
        "on_failure_callback": [task_failure_email_alert(["data-team@example.com"])],
    }

Design notes:

- Delivery uses the SMTP provider ``SmtpHook`` with the ``smtp_default``
  Connection stored in the metadata DB: host, port, credentials and TLS come
  from the Connection, so it works the same in the scheduler and in ephemeral
  task pods, without ``AIRFLOW__SMTP__*`` variables in the pod template.
- With ``retries > 0`` Airflow fires the callback once, after the final
  failed attempt: no duplicate alerts.
- The callback never raises: an alerting problem must not mask the task
  failure nor break the scheduler loop.
- It is imported at DAG parse time (callbacks are needed to build the DAG),
  so this module only uses the standard library at import time.
"""

from __future__ import annotations

import html as html_lib
import logging
import os
from datetime import UTC, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# Injected by helm/values.yaml and the pod template (see config/platform.env).
DEFAULT_BASE_URL = os.environ.get("AIRFLOW_BASE_URL", "http://localhost:8080")
DEFAULT_TIMEZONE = os.environ.get("ALERT_TIMEZONE", "UTC")
MAX_REASON_LENGTH = 2000


def _to_local_string(dt: datetime | None, tz_name: str = DEFAULT_TIMEZONE) -> str:
    """tz-aware datetime -> ``'YYYY-MM-DD HH:MM:SS (TZ)'`` in ``tz_name``."""
    if dt is None:
        return "N/A"
    local = dt.astimezone(ZoneInfo(tz_name))
    return f"{local:%Y-%m-%d %H:%M:%S} ({tz_name})"


def task_url(base_url: str, dag_id: str, run_id: str, task_id: str) -> str:
    """Deep link to a task instance in the Airflow 3 UI (logs tab by default)."""
    return (
        f"{base_url.rstrip('/')}/dags/{quote(str(dag_id), safe='')}"
        f"/runs/{quote(str(run_id), safe='')}"
        f"/tasks/{quote(str(task_id), safe='')}"
    )


def dag_url(base_url: str, dag_id: str) -> str:
    """Link to a DAG page in the Airflow 3 UI."""
    return f"{base_url.rstrip('/')}/dags/{quote(str(dag_id), safe='')}"


def render_failure_email(
    *,
    dag_id: str,
    task_id: str,
    run_id: str,
    logical_date: datetime | None,
    start_date: datetime | None,
    failure_date: datetime | None,
    reason: object,
    try_number: object,
    operator: str,
    base_url: str = DEFAULT_BASE_URL,
    tz_name: str = DEFAULT_TIMEZONE,
) -> tuple[str, str]:
    """Build ``(subject, html_body)``. Pure function: unit-testable without Airflow."""
    failed_local = _to_local_string(failure_date, tz_name)
    subject = f"[Airflow] FAILURE: {dag_id}.{task_id} — {failed_local}"

    safe_reason = html_lib.escape(str(reason or "No exception captured (see task logs)."))
    if len(safe_reason) > MAX_REASON_LENGTH:
        safe_reason = safe_reason[:MAX_REASON_LENGTH] + "\n[... truncated ...]"

    def row(label: str, value: object, mono: bool = False) -> str:
        font = "font-family:Consolas,Menlo,monospace;" if mono else ""
        return (
            "<tr>"
            f'<td style="padding:8px 14px;color:#6b7280;font-size:13px;white-space:nowrap;">{label}</td>'
            f'<td style="padding:8px 14px;color:#111827;font-size:13px;{font}">'
            f"{html_lib.escape(str(value))}</td></tr>"
        )

    rows = "".join(
        [
            row("DAG", dag_id, mono=True),
            row("Task", task_id, mono=True),
            row("Run ID", run_id, mono=True),
            row("Logical date", _to_local_string(logical_date, tz_name)),
            row("Run started", _to_local_string(start_date, tz_name)),
            row("Failed at", failed_local),
            row("Attempt", try_number),
            row("Operator", operator),
        ]
    )
    body = f"""
<div style="padding:24px;background:#f3f4f6;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:10px;border:1px solid #e5e7eb;overflow:hidden;">
    <div style="background:#b91c1c;padding:20px 26px;color:#fff;">
      <div style="font-size:18px;font-weight:700;">Airflow task failure</div>
      <div style="color:#fecaca;font-size:13px;margin-top:4px;">A task ended in <b>FAILED</b> state.</div>
    </div>
    <div style="padding:20px 26px 8px;">
      <table style="width:100%;border-collapse:collapse;background:#f9fafb;border:1px solid #e5e7eb;">{rows}</table>
    </div>
    <div style="padding:12px 26px 4px;">
      <div style="color:#374151;font-size:13px;font-weight:600;margin-bottom:6px;">Failure reason</div>
      <pre style="margin:0;padding:14px;background:#111827;color:#f87171;font-size:12px;border-radius:8px;white-space:pre-wrap;word-break:break-word;">{safe_reason}</pre>
    </div>
    <div style="padding:20px 26px 26px;">
      <a href="{task_url(base_url, dag_id, run_id, task_id)}" style="background:#b91c1c;color:#fff;text-decoration:none;font-size:13px;font-weight:600;padding:10px 18px;border-radius:6px;margin-right:10px;">View task logs</a>
      <a href="{dag_url(base_url, dag_id)}" style="color:#374151;text-decoration:none;font-size:13px;font-weight:600;padding:9px 18px;border-radius:6px;border:1px solid #d1d5db;">Open DAG</a>
    </div>
  </div>
</div>
"""
    return subject, body


def _deliver_email(recipients: list[str], subject: str, body: str, smtp_conn_id: str, sender: str | None) -> None:
    from airflow.providers.smtp.hooks.smtp import SmtpHook

    with SmtpHook(smtp_conn_id=smtp_conn_id) as hook:
        hook.send_email_smtp(to=recipients, subject=subject, html_content=body, from_email=sender)


def task_failure_email_alert(
    recipients: str | list[str],
    base_url: str = DEFAULT_BASE_URL,
    smtp_conn_id: str = "smtp_default",
    sender: str | None = None,
    tz_name: str = DEFAULT_TIMEZONE,
):
    """Return an ``on_failure_callback`` that emails an HTML alert to ``recipients``.

    ``sender`` is optional: if omitted, the ``from_email`` of the SMTP
    Connection extras is used.
    """
    if isinstance(recipients, str):
        recipients = [recipients]

    def _send_failure_alert(context) -> None:
        try:
            ti = context["task_instance"]
            subject, body = render_failure_email(
                dag_id=getattr(ti, "dag_id", "unknown"),
                task_id=getattr(ti, "task_id", "unknown"),
                run_id=getattr(ti, "run_id", context.get("run_id", "unknown")),
                logical_date=context.get("logical_date"),
                start_date=getattr(ti, "start_date", None),
                failure_date=getattr(ti, "end_date", None) or datetime.now(UTC),
                reason=context.get("exception"),
                try_number=getattr(ti, "try_number", "N/A"),
                operator=getattr(ti, "operator", "") or type(getattr(ti, "task", "")).__name__,
                base_url=base_url,
                tz_name=tz_name,
            )
            _deliver_email(recipients, subject, body, smtp_conn_id, sender)
            log.info("Failure alert emailed to %s", recipients)
        except Exception:  # noqa: BLE001 — alerting must never mask the task failure
            log.exception("Could not send failure alert email")

    return _send_failure_alert
