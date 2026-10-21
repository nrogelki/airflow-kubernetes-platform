#!/usr/bin/env bash
# deploy.sh — install/upgrade Airflow with the official Helm chart using the
# rendered helm/values.yaml.
#
# Usage: scripts/deploy.sh [--dry-run]
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

load_env
require_vars AIRFLOW_NAMESPACE HELM_RELEASE PROJECT_PATH
require_cmd helm

VALUES="$REPO_ROOT/helm/values.yaml"
POD_TEMPLATE="$REPO_ROOT/k8s/pod_templates/pod_template.yaml"
[ -f "$VALUES" ] && [ -f "$POD_TEMPLATE" ] || die "Falta configuración renderizada. Ejecuta: make render"

# hostPath volumes use type: Directory -> pods never start if a folder is missing.
for d in dags libs files logs k8s/pod_templates; do
    [ -d "$PROJECT_PATH/$d" ] || die "No existe $PROJECT_PATH/$d en el nodo. Ejecuta: make bootstrap"
done

repos="$(helm repo list 2>/dev/null || true)"  # captured: `| grep -q` + pipefail can SIGPIPE
grep -q '^apache-airflow' <<<"$repos" || helm repo add apache-airflow https://airflow.apache.org
helm repo update apache-airflow >/dev/null

kube get namespace "$AIRFLOW_NAMESPACE" >/dev/null 2>&1 \
    || kube create namespace "$AIRFLOW_NAMESPACE"

HELM_ARGS=(upgrade --install "$HELM_RELEASE" apache-airflow/airflow
    --namespace "$AIRFLOW_NAMESPACE" -f "$VALUES" --timeout 15m)
[ -n "${AIRFLOW_CHART_VERSION:-}" ] && HELM_ARGS+=(--version "$AIRFLOW_CHART_VERSION")
[ "${1:-}" = "--dry-run" ] && HELM_ARGS+=(--dry-run)

info "helm ${HELM_ARGS[*]}"
helm "${HELM_ARGS[@]}"

ok "Despliegue enviado. Sigue el arranque con: make status   (o: $KUBECTL get pods -n $AIRFLOW_NAMESPACE -w)"
info "UI: http://${SERVER_IP:-<SERVER_IP>}:${NODE_PORT}"
