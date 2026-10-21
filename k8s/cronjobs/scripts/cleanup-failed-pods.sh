#!/bin/sh
# cleanup-failed-pods.sh — deletes failed / stuck pods of the Airflow namespace.
# Source of the ConfigMap "pod-cleaner-script" (see kustomization.yaml).
# Runs inside the pod-cleaner CronJob (image with kubectl + GNU date).
#
# Env: NAMESPACE (default airflow) · DRY_RUN=1 -> only report, delete nothing.
NS="${NAMESPACE:-airflow}"
DRY_RUN="${DRY_RUN:-0}"
MIN_AGE_SEC=600   # do not touch pods younger than 10 min (transient states)
BAD_REASONS="ImagePullBackOff|ErrImagePull|CrashLoopBackOff|CreateContainerConfigError|CreateContainerError|InvalidImageName|RunContainerError|StartError|ContainerStatusUnknown"

echo "[cleaner] cleaning failed pods in ns=$NS — $(date -u +%FT%TZ)"

# ---- 1) Pods in phase=Failed (Error, Evicted, DeadlineExceeded...) --
if [ "$DRY_RUN" = "1" ]; then
  echo "[cleaner] DRY_RUN: pods in phase=Failed that would be deleted:"
  kubectl get pods -n "$NS" --field-selector=status.phase=Failed --no-headers 2>/dev/null || true
else
  kubectl delete pods -n "$NS" --field-selector=status.phase=Failed \
    --ignore-not-found=true --wait=false
fi

# ---- 2) Pods stuck in container error reasons -----------
NOW=$(date +%s)
# shellcheck disable=SC2016  # go-template, not shell expansion
kubectl get pods -n "$NS" \
  -o go-template='{{range .items}}{{$n := .metadata.name}}{{$t := .metadata.creationTimestamp}}{{range .status.containerStatuses}}{{if .state.waiting}}{{$n}}|{{.state.waiting.reason}}|{{$t}}{{"\n"}}{{end}}{{end}}{{end}}' \
  > /tmp/pods_waiting.txt || true

while IFS='|' read -r NAME REASON TS; do
  [ -z "$NAME" ] && continue
  echo "$REASON" | grep -Eq "$BAD_REASONS" || continue
  TS_SEC=$(date -d "$TS" +%s 2>/dev/null) || continue
  AGE=$(( NOW - TS_SEC ))
  if [ "$AGE" -lt "$MIN_AGE_SEC" ]; then
    echo "[cleaner] $NAME in $REASON but only ${AGE}s old — skipping for now."
    continue
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo "[cleaner] DRY_RUN: would delete $NAME ($REASON, ${AGE}s)."
  else
    echo "[cleaner] Deleting $NAME ($REASON, ${AGE}s)..."
    kubectl delete pod -n "$NS" "$NAME" --ignore-not-found=true --wait=false
  fi
done < /tmp/pods_waiting.txt

echo "[cleaner] cleanup finished."
