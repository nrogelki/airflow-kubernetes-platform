#!/usr/bin/env bash
# build_image.sh — build the immutable Airflow image and import it into the
# MicroK8s containerd (MicroK8s does not use the Docker daemon to run pods).
#
# Usage: scripts/build_image.sh [--no-import]
#
# To ship a dependency change: bump AIRFLOW_IMAGE_TAG in platform.env,
# rebuild, `make render` and `make deploy`. Never overwrite a tag in place.
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

load_env
require_vars AIRFLOW_IMAGE_REPO AIRFLOW_IMAGE_TAG AIRFLOW_VERSION AIRFLOW_PYTHON_VERSION
require_cmd docker

IMPORT=1
[ "${1:-}" = "--no-import" ] && IMPORT=0

SUDO=""
docker info >/dev/null 2>&1 || SUDO="sudo"

IMAGE="${AIRFLOW_IMAGE_REPO}:${AIRFLOW_IMAGE_TAG}"
info "Construyendo $IMAGE (apache/airflow:${AIRFLOW_VERSION}-python${AIRFLOW_PYTHON_VERSION})"
$SUDO docker build \
    --build-arg AIRFLOW_VERSION="$AIRFLOW_VERSION" \
    --build-arg PYTHON_VERSION="$AIRFLOW_PYTHON_VERSION" \
    -t "$IMAGE" "$REPO_ROOT/docker/airflow"
ok "Imagen construida: $IMAGE"

if [ "$IMPORT" -eq 1 ]; then
    require_cmd microk8s
    info "Importando $IMAGE a containerd de MicroK8s"
    # Remove the old one first: same tag would otherwise stay cached.
    sudo microk8s ctr images rm "docker.io/library/$IMAGE" >/dev/null 2>&1 || true
    $SUDO docker save "$IMAGE" | sudo microk8s ctr image import -
    # Capture first, then grep: `ctr ... | grep -q` under pipefail fails with SIGPIPE
    # (rc 141) as soon as containerd holds enough images, even if the image is there.
    images="$(sudo microk8s ctr images ls -q)"
    grep -qxF "docker.io/library/$IMAGE" <<<"$images" || die "La imagen no aparece en containerd"
    ok "Imagen disponible en containerd"
fi
