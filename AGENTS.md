# AGENTS.md — Guía para agentes de IA

Punto de entrada agnóstico de modelo (Codex, Cursor, Gemini CLI, Claude Code...) para
trabajar en este repositorio. `CLAUDE.md` solo importa este archivo.

## Qué es

Plataforma de Apache Airflow 3 con KubernetesExecutor sobre MicroK8s de un nodo. Tu
trabajo típico: **crear y mantener DAGs** y building blocks siguiendo la arquitectura
existente. No rediseñes la infraestructura salvo que se pida explícitamente.

## Leer antes de tocar

1. `README.md` — visión general y estructura.
2. `docs/05-desarrollo-de-dags.md` — el estándar de código (regla central).
3. `docs/06-files-y-permisos.md` y `docs/13-libreria-dataplatform.md`.

## Crear un DAG

```bash
scripts/create_dag.sh <dag_id> -s "<cron>" -a "<emails>"
# lógica en dags/<dag_id>/scripts/, orquestación en _dag.py, inputs en files/<dag_id>/
python3 tools/check_dags.py <dag_id>      # no debe quedar en FAIL
make test
```

## Reglas obligatorias

1. Lo pesado va en `@task.external_python(python="/opt/conda/envs/p313/bin/python")`.
2. Imports de `dataplatform.*` y `<dag_id>.scripts.*` **dentro** de las tareas. A nivel
   global de `_dag.py` solo decoradores, operadores y callbacks de alertas.
3. Solo primitivos entre tareas (rutas, dicts). Nunca DataFrames por XCom.
4. Credenciales solo por `conn_id`. Nunca en código, `files/` ni git.
5. `files/<dag_id>/` con el nombre exacto del `dag_id`; nada de código ahí.
6. Código compartido a `libs/dataplatform/` solo si lo usan 2+ DAGs, con tests. Lo que
   se importa al parsear debe ser compatible con Python 3.12 (imagen); el resto corre en
   3.13 (entorno).
7. `catchup=False`, `max_active_runs=1`, cargas idempotentes, alertas de fallo.
8. Toda variable nueva de plantilla: en `config/platform.env.example` **y** en `VARS`
   de `scripts/render_config.sh`.

## No hacer

- Instalar librerías de datos en `docker/airflow/requirements.txt`.
- Commitear `config/platform.env`, `helm/values.yaml`, `pod_template.yaml`, keytabs,
  exports de Connections o cualquier secreto.
- Dejar `.py` sueltos en la raíz de `dags/`.

## Verificación

`make lint test check-dags` debe pasar antes de proponer cambios.
