#!/usr/bin/env bash
# create_dag.sh — scaffold a new DAG following the platform layout:
#   dags/<dag_id>/{_dag.py, README.md, scripts/, sql/}  +  files/<dag_id>/
#
# Usage:
#   scripts/create_dag.sh <dag_id> [flags]        (or: make new-dag NAME=<dag_id>)
#
# Flags:
#   -s "<cron>"    Schedule (default: None = manual trigger only)
#   -o <owner>     Airflow owner in default_args (default: data-team)
#   -a "<emails>"  Comma-separated recipients: wires the failure email alert
#   -z <timezone>  DAG timezone (default: UTC)
#   -q             Do not create sql/
#   -f             Overwrite an existing _dag.py
#   -h             Help
#
# Example:
#   scripts/create_dag.sh sales_daily_load -s "0 6 * * *" -a "data@example.com"
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

[ $# -ge 1 ] || usage 1
case "$1" in -h|--help) usage ;; esac

DAG_ID="$1"; shift
[[ "$DAG_ID" =~ ^[a-z][a-z0-9_]*$ ]] || die "dag_id debe ser snake_case ([a-z][a-z0-9_]*): '$DAG_ID'"

SCHEDULE=""; OWNER="data-team"; ALERTS=""; TZ_NAME="UTC"; MAKE_SQL=1; FORCE=0
while getopts ":s:o:a:z:qfh" opt; do
    case "$opt" in
        s) SCHEDULE="$OPTARG" ;;
        o) OWNER="$OPTARG" ;;
        a) ALERTS="$OPTARG" ;;
        z) TZ_NAME="$OPTARG" ;;
        q) MAKE_SQL=0 ;;
        f) FORCE=1 ;;
        h) usage ;;
        \?) die "Flag desconocido: -$OPTARG" ;;
        :)  die "El flag -$OPTARG necesita un valor" ;;
    esac
done

[ -f "$ENV_FILE" ] && load_env
PYTHON_ENV_NAME="${PYTHON_ENV_NAME:-p313}"
AIRFLOW_UID="${AIRFLOW_UID:-50000}"
DEV_GROUP="${DEV_GROUP:-developers}"

DAG_DIR="$REPO_ROOT/dags/$DAG_ID"
FILES_DIR="$REPO_ROOT/files/$DAG_ID"
DAG_PY="$DAG_DIR/_dag.py"

if [ -s "$DAG_PY" ] && [ "$FORCE" -ne 1 ]; then
    die "$DAG_PY ya existe. Usa -f para sobrescribir."
fi

mkdir -p "$DAG_DIR/scripts" "$FILES_DIR"
[ "$MAKE_SQL" -eq 1 ] && mkdir -p "$DAG_DIR/sql" && touch "$DAG_DIR/sql/.gitkeep"
touch "$DAG_DIR/scripts/__init__.py" "$FILES_DIR/.gitkeep"

if [ -n "$SCHEDULE" ]; then SCHEDULE_PY="\"$SCHEDULE\""; else SCHEDULE_PY="None"; fi

ALERTS_IMPORT=""; ALERTS_ARG=""
if [ -n "$ALERTS" ]; then
    RECIPIENTS_PY=$(echo "$ALERTS" | awk -F',' '{
        for (i=1; i<=NF; i++) { gsub(/^ +| +$/, "", $i); printf "%s\"%s\"", (i>1?", ":""), $i }
    }')
    ALERTS_IMPORT=$'\n\n''from dataplatform.alerts.email_alerts import task_failure_email_alert'
    ALERTS_ARG=$'\n'"    \"on_failure_callback\": [task_failure_email_alert([$RECIPIENTS_PY])],"
fi

TODAY="$(date +%Y,\ %-m,\ %-d)"

cat > "$DAG_PY" <<EOF
"""${DAG_ID} — TODO: describe what this pipeline does (source -> target)."""

from datetime import timedelta

import pendulum
from airflow.sdk import dag, task${ALERTS_IMPORT}

# Isolated environment for heavy work (mounted read-only in every task pod).
PYTHON_ENV = "/opt/conda/envs/${PYTHON_ENV_NAME}/bin/python"
# Per-DAG data folder (inputs + runtime staging). Mirrors dags/<dag_id>/.
LOCAL_PATH = "/opt/airflow/files/${DAG_ID}"

default_args = {
    "owner": "${OWNER}",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),${ALERTS_ARG}
}


# -- Tasks: thin orchestration. Imports of dataplatform.* and scripts/ go INSIDE.


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def run(local_path: str) -> dict:
    import sys

    if "/opt/airflow/dags" not in sys.path:
        sys.path.insert(0, "/opt/airflow/dags")
    from ${DAG_ID}.scripts.${DAG_ID}_etl import run_etl

    return run_etl(local_path)


@dag(
    dag_id="${DAG_ID}",
    description="TODO: one-line description",
    default_args=default_args,
    start_date=pendulum.datetime(${TODAY}, tz="${TZ_NAME}"),
    schedule=${SCHEDULE_PY},
    catchup=False,
    max_active_runs=1,
    tags=["under-development"],
)
def ${DAG_ID}():
    run(LOCAL_PATH)


${DAG_ID}()
EOF

cat > "$DAG_DIR/scripts/${DAG_ID}_etl.py" <<EOF
"""Business logic used exclusively by the ${DAG_ID} DAG.

Plain Python: third-party imports at the top are fine here, this module only
runs inside the isolated environment. Anything reused by 2+ DAGs should be
promoted to libs/dataplatform/.
"""


def run_etl(local_path: str) -> dict:
    print(f"TODO: implement the ETL. Staging folder: {local_path}")
    return {"rows": 0}
EOF

cat > "$DAG_DIR/README.md" <<EOF
# ${DAG_ID}

**Qué hace:** TODO

| Campo | Valor |
|---|---|
| Schedule | \`${SCHEDULE:-manual}\` |
| Owner | ${OWNER} |
| Entorno | \`/opt/conda/envs/${PYTHON_ENV_NAME}\` |
| Connections (\`conn_id\`) | TODO |
| Origen → destino | TODO |
| Alertas | ${ALERTS:-sin alertas} |

## Flujo de tareas

\`run\` → TODO

## Inputs en \`files/${DAG_ID}/\`

TODO (o "ninguno").
EOF

# Data folder must be writable by the task pods (UID $AIRFLOW_UID).
if chown -R "$AIRFLOW_UID:$DEV_GROUP" "$FILES_DIR" 2>/dev/null \
    || sudo -n chown -R "$AIRFLOW_UID:$DEV_GROUP" "$FILES_DIR" 2>/dev/null; then
    chmod -R 775 "$FILES_DIR" 2>/dev/null || sudo -n chmod -R 775 "$FILES_DIR" || true
else
    warn "No se pudo asignar $FILES_DIR a $AIRFLOW_UID:$DEV_GROUP. Ejecuta:"
    warn "  sudo chown -R $AIRFLOW_UID:$DEV_GROUP $FILES_DIR && sudo chmod -R 775 $FILES_DIR"
fi

ok "DAG '$DAG_ID' creado:"
echo "   $DAG_PY"
echo "   $DAG_DIR/scripts/${DAG_ID}_etl.py"
echo "   $DAG_DIR/README.md"
echo "   $FILES_DIR/"
info "Siguiente: implementar scripts/, completar README y correr 'make check-dags'."
