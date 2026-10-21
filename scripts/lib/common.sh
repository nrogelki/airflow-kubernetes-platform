#!/usr/bin/env bash
# Shared helpers for every script in scripts/. Source it, do not execute it.
# shellcheck disable=SC2034  # variables are consumed by the sourcing scripts

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/config/platform.env}"

if [ -t 1 ]; then
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'; C_RESET=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_RESET=""
fi

info() { printf '%s[INFO]%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()   { printf '%s[ OK ]%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s[WARN]%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die()  { printf '%s[FAIL]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

# Load config/platform.env (or $ENV_FILE) and export every variable in it.
load_env() {
    [ -f "$ENV_FILE" ] || die "No existe $ENV_FILE. Ejecuta: cp config/platform.env.example config/platform.env"
    set -a
    # shellcheck source=/dev/null
    . "$ENV_FILE"
    set +a
}

# Fail if any of the given variable names is empty.
require_vars() {
    local missing=()
    local v
    for v in "$@"; do
        [ -n "${!v:-}" ] || missing+=("$v")
    done
    [ ${#missing[@]} -eq 0 ] || die "Variables vacías en $ENV_FILE: ${missing[*]}"
}

require_cmd() {
    local c
    for c in "$@"; do
        command -v "$c" >/dev/null 2>&1 || die "Falta el comando '$c' en el PATH."
    done
}

# Run kubectl through the configured prefix (e.g. "microk8s kubectl").
kube() {
    # shellcheck disable=SC2086  # KUBECTL is intentionally word-split
    ${KUBECTL:-kubectl} "$@"
}

# Persist KEY=VALUE into the env file (replaces the line if it exists).
set_env_value() {
    local key="$1" value="$2"
    if grep -qE "^${key}=" "$ENV_FILE"; then
        # '|' as sed delimiter: base64 keys may contain '/' and '+'.
        sed -i "s|^${key}=.*|${key}=\"${value}\"|" "$ENV_FILE"
    else
        printf '%s="%s"\n' "$key" "$value" >> "$ENV_FILE"
    fi
}
