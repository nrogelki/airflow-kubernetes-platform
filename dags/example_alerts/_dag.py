"""example_alerts — catalogue of alert templates (failure / retry / success).

Trigger it manually: `always_fails` fails on purpose after one retry so you
can see every channel fire. Create only the Connections you use and delete
the others from the lists below (a missing Connection is logged, never raised).

    Connection id          Type   Where the secret goes
    smtp_default           SMTP   host/port/login/password (+ extra from_email)
    slack_alerts           HTTP   Password = Slack Incoming Webhook URL
    teams_alerts           HTTP   Password = Teams "Workflows" webhook URL
    google_chat_alerts     HTTP   Password = Google Chat space webhook URL
    ops_webhook            HTTP   Password = any JSON endpoint URL

Callbacks are imported at module level on purpose: Airflow needs them when it
builds the DAG (parse time). dataplatform.alerts only uses the standard library
at import time, so this is safe for the dag-processor.
"""

from datetime import timedelta

import pendulum
from airflow.sdk import dag, task

from dataplatform.alerts.email_alerts import task_failure_email_alert
from dataplatform.alerts.webhooks import google_chat_alert, slack_alert, teams_alert, webhook_alert

PYTHON_ENV = "/opt/conda/envs/p313/bin/python"
RECIPIENTS = ["data-team@example.com"]

default_args = {
    "owner": "data-team",
    "retries": 1,
    "retry_delay": timedelta(seconds=30),
    # Fires once, after the LAST failed attempt.
    "on_failure_callback": [
        task_failure_email_alert(RECIPIENTS),
        slack_alert("slack_alerts"),
        teams_alert("teams_alerts"),
        google_chat_alert("google_chat_alerts"),
        webhook_alert("ops_webhook"),
    ],
    # Fires on every attempt that will be retried (early warning).
    "on_retry_callback": [slack_alert("slack_alerts", event="retry")],
}


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def always_fails() -> None:
    raise RuntimeError("Intentional failure to test the alert templates")


@dag(
    dag_id="example_alerts",
    description="Every alert template of dataplatform.alerts, wired to one DAG",
    default_args=default_args,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    # DAG-level callback: once per successful DAG run.
    on_success_callback=[slack_alert("slack_alerts", event="success")],
    tags=["example", "alerts"],
)
def example_alerts():
    always_fails()


example_alerts()
