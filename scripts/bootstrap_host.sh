#!/usr/bin/env bash
# bootstrap_host.sh — prepare the node: developers group, runtime directories
# and ownership/permissions expected by the hostPath volumes.
#
# Usage: sudo -E scripts/bootstrap_host.sh      (or: make bootstrap)
#
# Idempotent: safe to run again at any time (e.g. after a fresh clone).
#
# Permission model (see docs/06-files-y-permisos.md):
#   code (dags/, libs/, k8s/)  -> PROJECT_OWNER:DEV_GROUP, dirs 2775 (setgid)
#   data (files/, logs/)       -> AIRFLOW_UID:DEV_GROUP,   775
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

load_env
require_vars PROJECT_PATH PROJECT_OWNER DEV_GROUP AIRFLOW_UID
[ "$(id -u)" -eq 0 ] || die "Ejecutar con sudo: sudo -E $0"

if [ "$(realpath "$REPO_ROOT")" != "$(realpath -m "$PROJECT_PATH")" ]; then
    warn "El repo está en $REPO_ROOT pero PROJECT_PATH=$PROJECT_PATH."
    warn "Los volúmenes hostPath apuntarán a PROJECT_PATH: clona el repo ahí o corrige platform.env."
fi

getent group "$DEV_GROUP" >/dev/null || { groupadd "$DEV_GROUP"; ok "Grupo $DEV_GROUP creado"; }
id "$PROJECT_OWNER" >/dev/null 2>&1 || die "No existe el usuario $PROJECT_OWNER (créalo con: sudo adduser $PROJECT_OWNER)"
usermod -aG "$DEV_GROUP" "$PROJECT_OWNER"

cd "$REPO_ROOT"
mkdir -p dags libs files logs k8s/pod_templates

info "Dueño del código: $PROJECT_OWNER:$DEV_GROUP (setgid en directorios)"
chown -R "$PROJECT_OWNER:$DEV_GROUP" dags libs k8s tools scripts docs 2>/dev/null || true
find dags libs k8s -type d -exec chmod 2775 {} +
chmod -R g+rw dags libs k8s

info "Datos de runtime: $AIRFLOW_UID:$DEV_GROUP (los pods corren como UID $AIRFLOW_UID)"
chown -R "$AIRFLOW_UID:$DEV_GROUP" files logs
chmod -R 775 files logs

# Secrets must never be world-readable.
[ -f config/platform.env ] && chmod 640 config/platform.env && chgrp "$DEV_GROUP" config/platform.env

ok "Host preparado en $REPO_ROOT"
info "Recuerda: los usuarios agregados a $DEV_GROUP deben re-loguearse (o 'newgrp $DEV_GROUP')."
