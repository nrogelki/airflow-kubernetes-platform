#!/usr/bin/env bash
# install_microk8s.sh — install MicroK8s on a pinned channel with the addons
# this platform needs, and hold automatic snap refreshes.
#
# Usage: sudo scripts/install_microk8s.sh [--channel 1.35/stable] [--docker-fix] [--image-gc]
#
#   --docker-fix  Adds --advertise-address=0.0.0.0 to kube-apiserver. REQUIRED if
#                 the node also runs standalone Docker (docker network create/rm
#                 otherwise restarts the whole control plane). Single-node only.
#                 See docs/09-troubleshooting.md#reinicios-por-redes-de-docker
#   --image-gc    Raises kubelet image GC thresholds (95/90) so the locally
#                 imported Airflow image is not garbage-collected between runs.
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

CHANNEL="1.35/stable"
DOCKER_FIX=0
IMAGE_GC=0
while [ $# -gt 0 ]; do
    case "$1" in
        --channel) CHANNEL="$2"; shift 2 ;;
        --docker-fix) DOCKER_FIX=1; shift ;;
        --image-gc) IMAGE_GC=1; shift ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) die "Argumento desconocido: $1" ;;
    esac
done

[ "$(id -u)" -eq 0 ] || die "Ejecutar con sudo."
require_cmd snap

if snap list microk8s >/dev/null 2>&1; then
    info "MicroK8s ya instalado; moviendo al canal $CHANNEL"
    snap refresh microk8s --channel="$CHANNEL" || true
else
    info "Instalando MicroK8s ($CHANNEL)"
    snap install microk8s --classic --channel="$CHANNEL"
fi

# Freeze automatic refreshes: a surprise minor upgrade can break the chart or Calico.
snap refresh --hold microk8s
microk8s status --wait-ready

for addon in dns hostpath-storage rbac metrics-server; do
    microk8s enable "$addon"
done

ARGS_DIR=/var/snap/microk8s/current/args
restart_needed=0

if [ "$DOCKER_FIX" -eq 1 ]; then
    if ! grep -q -- '--advertise-address' "$ARGS_DIR/kube-apiserver"; then
        cp "$ARGS_DIR/kube-apiserver" "$ARGS_DIR/kube-apiserver.bak.$(date +%Y%m%d%H%M%S)"
        echo '--advertise-address=0.0.0.0' >> "$ARGS_DIR/kube-apiserver"
        restart_needed=1
        ok "Fix de redes Docker aplicado (--advertise-address=0.0.0.0)"
    fi
fi

if [ "$IMAGE_GC" -eq 1 ]; then
    cp "$ARGS_DIR/kubelet" "$ARGS_DIR/kubelet.bak.$(date +%Y%m%d%H%M%S)"
    sed -i '/--image-gc-high-threshold/d;/--image-gc-low-threshold/d' "$ARGS_DIR/kubelet"
    printf '%s\n' '--image-gc-high-threshold=95' '--image-gc-low-threshold=90' >> "$ARGS_DIR/kubelet"
    restart_needed=1
    ok "Umbrales de image GC del kubelet: 95/90"
fi

if [ "$restart_needed" -eq 1 ]; then
    microk8s stop && microk8s start
    microk8s status --wait-ready
fi

microk8s version
ok "MicroK8s listo. Agrega a los developers al grupo: sudo usermod -aG microk8s <usuario>"
