# example_alerts

**Qué hace:** catálogo de plantillas de alertas de `dataplatform.alerts`
cableadas a un DAG que falla a propósito (1 reintento), para probar cada canal.

| Evento | Callback | Canales de ejemplo |
|---|---|---|
| Fallo definitivo | `on_failure_callback` (default_args) | Email, Slack, Teams, Google Chat, webhook genérico |
| Reintento | `on_retry_callback` (default_args) | Slack |
| Éxito del DAG run | `on_success_callback` (`@dag`) | Slack |

Connections requeridas (crear solo las que uses): ver docstring de `_dag.py`
y [`docs/12-alertas.md`](../../docs/12-alertas.md).
