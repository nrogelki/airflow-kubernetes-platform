#!/usr/bin/env bash
# repair_conda_env.sh — rewrite every pip package of the isolated environment at
# EXACTLY the versions frozen in envs/<env>/environment.lock.yml (pip: section).
#
# When: packages "installed" according to `pip list` but with corrupt/partial
# files (ModuleNotFoundError / "unknown location" on imports that used to work),
# typically after an interrupted install or a disk-full event. Instead of hunting
# broken packages one by one, this reinstalls all of them without changing a
# single version (--force-reinstall --no-deps).
#
# Usage: sudo -E scripts/repair_conda_env.sh [lock-file]
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

load_env
require_vars CONDA_ENVS_HOST_PATH PYTHON_ENV_NAME

PY="$CONDA_ENVS_HOST_PATH/$PYTHON_ENV_NAME/bin/python"
LOCK="${1:-$REPO_ROOT/envs/$PYTHON_ENV_NAME/environment.lock.yml}"
[ -x "$PY" ] || die "No existe el entorno: $PY (usa make conda-env)"
[ -f "$LOCK" ] || die "No existe el lock $LOCK (se genera con make conda-env)"

# Only the name==version pins of the lock's pip: section (conda packages such as
# python or openssl are not touched; for those: make conda-env ARGS=--recreate).
PKGS_FILE="$(mktemp)"
trap 'rm -f "$PKGS_FILE"' EXIT
sed -nE 's/^[[:space:]]+-[[:space:]]+([A-Za-z0-9_.-]+(\[[^]]*\])?==[^[:space:]]+)[[:space:]]*$/\1/p' "$LOCK" > "$PKGS_FILE"
[ -s "$PKGS_FILE" ] || die "El lock $LOCK no tiene paquetes pip fijados (name==version)"

info "Reinstalando $(wc -l < "$PKGS_FILE") paquetes de $LOCK (mismas versiones, --no-deps)"
"$PY" -m pip install --force-reinstall --no-deps --no-cache-dir -r "$PKGS_FILE"
"$PY" -m pip check || warn "pip check reporta inconsistencias (revisar arriba)"
chmod -R a+rX "$CONDA_ENVS_HOST_PATH/$PYTHON_ENV_NAME"
ok "Entorno reparado: $CONDA_ENVS_HOST_PATH/$PYTHON_ENV_NAME"
