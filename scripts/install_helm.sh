#!/usr/bin/env bash
# install_helm.sh — install a PINNED Helm binary (not the auto-updating snap)
# and register the official Apache Airflow chart repository.
#
# Usage: sudo scripts/install_helm.sh [version]      (default: v3.19.2)
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

HELM_VERSION="${1:-v3.19.2}"
[ "$(id -u)" -eq 0 ] || die "Ejecutar con sudo."
require_cmd curl tar

case "$(uname -m)" in
    x86_64)  ARCH=amd64 ;;
    aarch64) ARCH=arm64 ;;
    *) die "Arquitectura no soportada: $(uname -m)" ;;
esac

snap remove helm >/dev/null 2>&1 || true

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz" -o "$TMP/helm.tgz"
curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz.sha256sum" -o "$TMP/helm.sha256"
(cd "$TMP" && echo "$(awk '{print $1}' helm.sha256)  helm.tgz" | sha256sum -c -)
tar -xzf "$TMP/helm.tgz" -C "$TMP"
install -m 0755 "$TMP/linux-${ARCH}/helm" /usr/local/bin/helm

helm version
ok "Helm $HELM_VERSION instalado en /usr/local/bin/helm"
info "Cada usuario que use helm debe ejecutar (se guarda en su \$HOME):"
info "  helm repo add apache-airflow https://airflow.apache.org && helm repo update"
