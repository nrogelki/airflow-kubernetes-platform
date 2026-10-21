# 12 · Alertas

Todo DAG productivo debe avisar cuando falla. La plataforma trae **plantillas listas**
en [`libs/dataplatform/alerts/`](../libs/dataplatform/alerts/) y un DAG que las usa todas:
[`example_alerts`](../dags/example_alerts/).

## 1. Catálogo de plantillas

| Plantilla | Canal | Eventos | Connection |
|---|---|---|---|
| `task_failure_email_alert(recipients)` | Email HTML | fallo | `smtp_default` (SMTP) |
| `slack_alert(conn_id, event=)` | Slack (Block Kit) | fallo · reintento · éxito | HTTP, URL en *Password* |
| `teams_alert(conn_id, event=)` | Microsoft Teams (Adaptive Card) | fallo · reintento · éxito | HTTP, URL en *Password* |
| `google_chat_alert(conn_id, event=)` | Google Chat | fallo · reintento · éxito | HTTP, URL en *Password* |
| `webhook_alert(conn_id, event=)` | Cualquier endpoint JSON (n8n, PagerDuty vía proxy, API propia) | fallo · reintento · éxito | HTTP, URL en *Password* |

Todas comparten tres garantías:

1. **Nunca lanzan excepción.** Si el SMTP o el webhook caen, se registra en el log y la
   tarea sigue marcada como fallida (el problema de alerta no tapa el problema real).
2. **Sin secretos en el código.** Destinos y credenciales viven en Connections.
3. **Enlace directo** a la tarea en la UI (usa `AIRFLOW_BASE_URL`, que `values.yaml` y el
   `pod_template` inyectan desde `platform.env`) y hora en `ALERT_TIMEZONE`.

## 2. Cómo se cablean

```python
from dataplatform.alerts.email_alerts import task_failure_email_alert
from dataplatform.alerts.webhooks import slack_alert, teams_alert

default_args = {
    "retries": 2,
    # Una vez, tras el ÚLTIMO intento fallido:
    "on_failure_callback": [
        task_failure_email_alert(["data-team@example.com", "oncall@example.com"]),
        teams_alert("teams_alerts"),
    ],
    # En cada intento que se va a reintentar (aviso temprano):
    "on_retry_callback": [slack_alert("slack_alerts", event="retry")],
}

@dag(
    default_args=default_args,
    # A nivel DAG: una vez por corrida exitosa (útil para reportes críticos)
    on_success_callback=[slack_alert("slack_alerts", event="success")],
)
```

- Los callbacks son **listas**: combina canales libremente.
- En `default_args` aplican a **cada tarea**; en `@dag(...)` aplican a la **corrida**.
- Se importan a nivel global del `_dag.py` (Airflow los necesita al construir el DAG).
  Por eso `dataplatform.alerts` solo usa la librería estándar al importarse.
- `create_dag.sh -a "a@x.com,b@x.com"` deja el email cableado automáticamente.

## 3. Cómo interpreta Airflow la conexión de correo `smtp_default`

Este punto confunde a mucha gente al pasar de Celery a Kubernetes, así que va en detalle.

### 3.1 Dos mecanismos distintos de envío

| Mecanismo | Lee la configuración de | ¿Funciona en Pods de tarea efímeros? |
|---|---|---|
| **Legacy**: `email_on_failure=True` / `airflow.utils.email.send_email` | Sección `[smtp]` de `airflow.cfg` o variables `AIRFLOW__SMTP__*` **del proceso que envía** | Solo si repites esas variables en el `pod_template`. Si no → intenta `localhost:25` → `ConnectionRefusedError` |
| **Provider SMTP** (`SmtpHook`, `SmtpNotifier`, nuestra plantilla) | La **Connection** `smtp_default` | **Sí**: la Connection se resuelve igual desde cualquier Pod |

Con Celery el primer mecanismo "funcionaba" porque los workers eran contenedores
permanentes con el `airflow.cfg` completo. Con KubernetesExecutor el callback de fallo
se ejecuta **dentro del Pod de la tarea**, que no tiene esa configuración. Por eso la
plantilla usa `SmtpHook(smtp_conn_id="smtp_default")`: la config viaja con la Connection.
(En Airflow 3, además, `email_on_failure` está deprecado en favor de *notifiers* y
callbacks.)

### 3.2 Dónde busca Airflow la Connection (en orden)

1. **Secrets backend** configurado (`[secrets] backend`: Vault, AWS SM, GCP SM...).
2. **Variable de entorno** `AIRFLOW_CONN_SMTP_DEFAULT` (URI o JSON).
3. **Metadata DB** (lo que creas en Admin → Connections), cifrada con la Fernet key.

La primera que encuentra gana. Lo habitual aquí es la opción 3.

Dos precisiones (verificadas en Airflow 3.2.1):

- Las **tareas** (y sus callbacks de alerta, que corren en el mismo Pod) no leen la
  metadata DB directamente: piden la Connection al api-server por la *Execution API*, que
  la lee de la DB. Para ti no cambia nada: lo que creas en Admin → Connections funciona.
- La variable `AIRFLOW_CONN_...` (opción 2) debe existir **donde corre el código**: para
  alertas y tareas, en el Pod de tarea, o sea en el `env` de
  `k8s/pod_templates/pod_template.template.yaml`. Si solo la pones en el `env` de
  `helm/values.template.yaml`, no llega a las tareas
  ([04 §4](04-configuracion.md#4-personalizaciones-frecuentes)).

### 3.3 Cómo lee cada campo `SmtpHook`

| Campo de la Connection | Uso |
|---|---|
| **Host** | Servidor SMTP (`smtp.gmail.com`, `smtp.office365.com`, relay interno) |
| **Port** | `465` (SSL implícito) o `587` (STARTTLS) o `25` (relay sin cifrado) |
| **Login / Password** | Credenciales. Vacíos = relay sin autenticación |
| Extra `from_email` | Remitente cuando la plantilla no recibe `sender` |
| Extra `disable_ssl` | `false` (default) → conecta con **SMTP_SSL** (puerto 465). `true` → SMTP plano |
| Extra `disable_tls` | Con `disable_ssl: true`: `false` (default) → hace **STARTTLS** (587). `true` → sin cifrado (25) |
| Extra `timeout`, `retry_limit` | Timeout de conexión y reintentos del envío |

> **El error más común:** configurar el puerto `587` sin `"disable_ssl": true`. El hook
> intenta SSL implícito sobre un puerto STARTTLS y falla con
> `SSL: WRONG_VERSION_NUMBER`. Regla: **465 → `disable_ssl: false`; 587 →
> `disable_ssl: true`**.

### 3.4 Ejemplos

**Office 365 / Gmail (STARTTLS, 587)** — en Gmail usa una *contraseña de aplicación*:

```
Conn Id:   smtp_default
Conn Type: SMTP
Host:      smtp.office365.com          (o smtp.gmail.com)
Port:      587
Login:     alertas@tuempresa.com
Password:  ********
Extra:     {"from_email": "Airflow <alertas@tuempresa.com>", "disable_ssl": true}
```

**SSL implícito (465):**

```
Port: 465
Extra: {"from_email": "alertas@tuempresa.com"}
```

**Relay interno sin autenticación (25):**

```
Host: relay.interno.local   Port: 25   Login/Password: vacíos
Extra: {"from_email": "airflow@tuempresa.com", "disable_ssl": true, "disable_tls": true}
```

**Por CLI** (dentro del scheduler, `make shell`):

```bash
airflow connections add smtp_default --conn-type smtp \
  --conn-host smtp.office365.com --conn-port 587 \
  --conn-login alertas@tuempresa.com --conn-password '********' \
  --conn-extra '{"from_email": "alertas@tuempresa.com", "disable_ssl": true}'
```

### 3.5 Probarla

Activa y ejecuta `example_alerts` (falla a propósito). En el log de la tarea debe
aparecer `Failure alert emailed to [...]`; si aparece `Could not send failure alert
email`, el traceback siguiente dice por qué (credenciales, puerto/SSL, firewall).

## 4. Webhooks de chat

1. Crea el webhook en la herramienta:
   - **Slack:** app → *Incoming Webhooks* → *Add New Webhook to Workspace*.
   - **Teams:** canal → *Workflows* → plantilla *Post to a channel when a webhook request is
     received* (el nombre exacto puede variar según la versión de Teams). Los "Office 365
     connectors" / *Incoming Webhook* clásicos dejaron de funcionar en mayo de 2026.
   - **Google Chat** (desde el navegador): espacio → *Apps & integrations* → *Add webhooks*.
2. Crea la Connection: **Conn Type `HTTP`**, pega la URL completa en **Password**: queda
   cifrada en la base y la API/UI la muestran como `***`. La URL nunca aparece en los logs
   (solo el `conn_id`).
3. Úsala: `slack_alert("slack_alerts")` (igual `teams_alert`, `google_chat_alert`,
   `webhook_alert`).

El Pod de tarea necesita salida a internet (o a tu proxy) hacia el dominio del webhook.

> Verificado en MicroK8s apuntando los tres a un receptor de prueba: cada uno llegó con
> HTTP 200 y en el formato que espera su servicio (Slack: `text` + bloques; Teams:
> `message` con Adaptive Card 1.4; Google Chat: `text`). Una falla del webhook se registra
> en el log pero **no** oculta la falla de la tarea.

## 5. Crear tu propia plantilla

Todas se construyen con dos piezas reutilizables de
[`alerts/base.py`](../libs/dataplatform/alerts/base.py):

```python
from dataplatform.alerts.base import build_alert_info, build_text
from dataplatform.alerts.webhooks import post_json, resolve_webhook_url


def discord_alert(conn_id: str, event: str = "failure"):
    def _callback(context):
        try:
            info = build_alert_info(context, event=event)  # normaliza el context
            post_json(resolve_webhook_url(conn_id), {"content": build_text(info)})
        except Exception:
            import logging

            logging.getLogger(__name__).exception("discord alert failed")

    return _callback
```

Si la publicas en `libs/dataplatform/alerts/`, agrega un test en
`tests/test_webhooks.py` para el *payload* (función pura).
