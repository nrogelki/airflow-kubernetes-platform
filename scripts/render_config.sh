#!/usr/bin/env bash
# render_config.sh — generate helm/values.yaml and k8s/pod_templates/pod_template.yaml
# from their *.template.yaml + config/platform.env.
#
# Usage: scripts/render_config.sh
#   - Generates WEBSERVER_SECRET_KEY (openssl rand -base64 32) if empty and saves it.
#   - Autodetects SERVER_IP (hostname -I) if empty (not persisted).
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

require_cmd envsubst
load_env

if [ -z "${WEBSERVER_SECRET_KEY:-}" ]; then
    require_cmd openssl
    WEBSERVER_SECRET_KEY="$(openssl rand -base64 32)"
    set_env_value WEBSERVER_SECRET_KEY "$WEBSERVER_SECRET_KEY"
    export WEBSERVER_SECRET_KEY
    ok "WEBSERVER_SECRET_KEY generada y guardada en $ENV_FILE"
fi

if [ -z "${SERVER_IP:-}" ]; then
    SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    [ -n "$SERVER_IP" ] || die "No se pudo detectar SERVER_IP; defínela en $ENV_FILE"
    export SERVER_IP
    info "SERVER_IP autodetectada: $SERVER_IP (fíjala en $ENV_FILE si el nodo tiene varias IPs)"
fi

require_vars PROJECT_PATH CONDA_ENVS_HOST_PATH PYTHON_ENV_NAME AIRFLOW_NAMESPACE HELM_RELEASE \
    AIRFLOW_IMAGE_REPO AIRFLOW_IMAGE_TAG NODE_PORT POSTGRES_STORAGE_SIZE \
    PARALLELISM MAX_ACTIVE_TASKS_PER_DAG WORKER_PODS_CREATION_BATCH_SIZE \
    WORKER_CPU_REQUEST WORKER_MEMORY_REQUEST WORKER_CPU_LIMIT WORKER_MEMORY_LIMIT \
    WORKER_ACTIVE_DEADLINE_SECONDS ALERT_TIMEZONE

case "$PROJECT_PATH" in /*) ;; *) die "PROJECT_PATH debe ser una ruta absoluta: '$PROJECT_PATH'";; esac
if [ "$NODE_PORT" -lt 30000 ] || [ "$NODE_PORT" -gt 32767 ]; then
    die "NODE_PORT debe estar en el rango 30000-32767 (es $NODE_PORT)"
fi

# shellcheck disable=SC2016  # literal ${VAR} list for envsubst, must not expand
# Only substitute OUR variables: any other '$' in the templates stays untouched.
VARS='${PROJECT_PATH} ${CONDA_ENVS_HOST_PATH} ${PYTHON_ENV_NAME} ${AIRFLOW_NAMESPACE} ${HELM_RELEASE}
${AIRFLOW_IMAGE_REPO} ${AIRFLOW_IMAGE_TAG} ${SERVER_IP} ${NODE_PORT} ${WEBSERVER_SECRET_KEY}
${STORAGE_CLASS} ${POSTGRES_STORAGE_SIZE} ${PARALLELISM} ${MAX_ACTIVE_TASKS_PER_DAG}
${WORKER_PODS_CREATION_BATCH_SIZE} ${WORKER_CPU_REQUEST} ${WORKER_MEMORY_REQUEST}
${WORKER_CPU_LIMIT} ${WORKER_MEMORY_LIMIT} ${WORKER_ACTIVE_DEADLINE_SECONDS} ${ALERT_TIMEZONE}'

render() {
    local src="$1" dst="$2"
    envsubst "$VARS" < "$src" > "$dst.tmp"
    mv "$dst.tmp" "$dst"
    chmod 640 "$dst"
    ok "Generado $dst"
}

# Output paths can be overridden (used by the test suite to render into a tmp dir).
VALUES_OUT="${VALUES_OUT:-$REPO_ROOT/helm/values.yaml}"
POD_TEMPLATE_OUT="${POD_TEMPLATE_OUT:-$REPO_ROOT/k8s/pod_templates/pod_template.yaml}"

render "$REPO_ROOT/helm/values.template.yaml"                    "$VALUES_OUT"
render "$REPO_ROOT/k8s/pod_templates/pod_template.template.yaml" "$POD_TEMPLATE_OUT"
# The scheduler (UID 50000) must be able to read the pod template.
chmod 644 "$POD_TEMPLATE_OUT"

info "values.yaml -> aplicar con 'make deploy'. pod_template.yaml -> 'make restart-scheduler'."
