#!/usr/bin/env bash
# doctor.sh — read-only health check of the host + cluster + Airflow.
#
# Usage: scripts/doctor.sh          (or: make doctor)
# Exit code 1 if any check FAILS (warnings do not fail).
set -uo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

load_env
FAILS=0
check() {  # check "<description>" <command...>
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then ok "$desc"; else printf '%s[FAIL]%s %s\n' "$C_RED" "$C_RESET" "$desc"; FAILS=$((FAILS + 1)); fi
}

echo "== Host =="
check "config/platform.env existe" test -f "$ENV_FILE"
check "helm/values.yaml renderizado" test -f "$REPO_ROOT/helm/values.yaml"
check "pod_template.yaml renderizado" test -f "$REPO_ROOT/k8s/pod_templates/pod_template.yaml"
for d in dags libs files logs k8s/pod_templates; do
    check "Directorio $PROJECT_PATH/$d" test -d "$PROJECT_PATH/$d"
done
check "files/ pertenece a UID ${AIRFLOW_UID}" test "$(stat -c %u "$PROJECT_PATH/files" 2>/dev/null)" = "$AIRFLOW_UID"
check "logs/ pertenece a UID ${AIRFLOW_UID}" test "$(stat -c %u "$PROJECT_PATH/logs" 2>/dev/null)" = "$AIRFLOW_UID"
check "Entorno Python $CONDA_ENVS_HOST_PATH/$PYTHON_ENV_NAME" test -x "$CONDA_ENVS_HOST_PATH/$PYTHON_ENV_NAME/bin/python"

DISK_PCT="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
if [ "${DISK_PCT:-0}" -ge 85 ]; then warn "Disco / al ${DISK_PCT}% (DiskPressure expulsa pods)"; else ok "Disco / al ${DISK_PCT}%"; fi

echo "== Kubernetes =="
check "kubectl responde" kube get nodes
check "Nodo Ready" bash -c "${KUBECTL} get nodes --no-headers | grep -qw Ready"
check "Imagen ${AIRFLOW_IMAGE_REPO}:${AIRFLOW_IMAGE_TAG} en containerd" \
    bash -c "sudo -n microk8s ctr images ls 2>/dev/null | grep -q '${AIRFLOW_IMAGE_REPO}:${AIRFLOW_IMAGE_TAG}'"
check "Namespace ${AIRFLOW_NAMESPACE}" kube get namespace "$AIRFLOW_NAMESPACE"

echo "== Airflow =="
# The chart deploys the triggerer as a StatefulSet when triggerer.persistence
# is enabled (its default) and as a Deployment otherwise: accept either kind.
rollout_ok() {
    kube rollout status "deployment/$1" -n "$AIRFLOW_NAMESPACE" --timeout=5s \
        || kube rollout status "statefulset/$1" -n "$AIRFLOW_NAMESPACE" --timeout=5s
}
for comp in scheduler dag-processor api-server triggerer; do
    check "${HELM_RELEASE}-${comp} disponible" rollout_ok "${HELM_RELEASE}-${comp}"
done
check "PostgreSQL Running" bash -c "${KUBECTL} get pods -n ${AIRFLOW_NAMESPACE} --no-headers | grep postgresql | grep -q Running"

BAD="$(kube get pods -n "$AIRFLOW_NAMESPACE" --no-headers 2>/dev/null | grep -Ec 'Error|CrashLoopBackOff|ImagePull|Evicted' || true)"
if [ "${BAD:-0}" -gt 0 ]; then warn "$BAD pod(s) en estado de error: make status"; else ok "Sin pods en estado de error"; fi

echo
if [ "$FAILS" -gt 0 ]; then die "$FAILS chequeo(s) fallaron. Ver docs/09-troubleshooting.md"; fi
ok "Todo en orden."
