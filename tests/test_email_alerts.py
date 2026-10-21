from datetime import UTC, datetime

from dataplatform.alerts import email_alerts as ea

WHEN = datetime(2026, 1, 15, 12, 30, tzinfo=UTC)


def _render(**overrides):
    kwargs = dict(
        dag_id="sales",
        task_id="load",
        run_id="manual__2026-01-15T12:00:00+00:00",
        logical_date=WHEN,
        start_date=WHEN,
        failure_date=WHEN,
        reason=ValueError("boom <b>"),
        try_number=3,
        operator="PythonOperator",
        base_url="http://10.0.0.1:31399",
        tz_name="UTC",
    )
    kwargs.update(overrides)
    return ea.render_failure_email(**kwargs)


def test_subject_contains_dag_task_and_time():
    subject, _ = _render()
    assert subject == "[Airflow] FAILURE: sales.load — 2026-01-15 12:30:00 (UTC)"


def test_reason_is_html_escaped():
    _, body = _render()
    assert "boom &lt;b&gt;" in body and "boom <b>" not in body


def test_links_are_url_encoded():
    _, body = _render()
    assert "http://10.0.0.1:31399/dags/sales/runs/manual__2026-01-15T12%3A00%3A00%2B00%3A00/tasks/load" in body


def test_timezone_conversion():
    subject, _ = _render(tz_name="America/Santiago")
    assert "09:30:00 (America/Santiago)" in subject


def test_long_reason_is_truncated():
    _, body = _render(reason="x" * 5000)
    assert "[... truncated ...]" in body


def test_callback_never_raises(monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(ea, "_deliver_email", explode)
    cb = ea.task_failure_email_alert("a@example.com")
    cb({"task_instance": object()})  # must not raise
