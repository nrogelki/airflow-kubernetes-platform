#!/bin/sh
# watchdog-calico.sh — restarts calico-node when the CNI loses API auth
# (event signature: plugin type="calico" failed ... Unauthorized).
# Source of the ConfigMap "calico-watchdog-script" (see kustomization.yaml).
#
# Safety locks: only RECENT events (EVENT_WINDOW_SEC) count, and a restart is
# blocked for COOLDOWN_SEC after the previous one (annotation on the DaemonSet).
# Env: DRY_RUN=1 -> detect and log, never restart.
DRY_RUN="${DRY_RUN:-0}"
NOW=$(date +%s)

# -------------------------------------------------------------------
# KEY CONFIGURATION
# -------------------------------------------------------------------
EVENT_WINDOW_SEC=900  # Looks for errors that occurred in the last 15 mins
COOLDOWN_SEC=3600     # Blocks new restarts for 1 HOUR (3600 seconds)

echo "[watchdog] Calico CNI health scan — $(date -u +%FT%TZ)"

# ---- Step A: Read the "Post-it" (Annotation) --------------------
LAST_RESTART=$(kubectl get ds calico-node -n kube-system -o=jsonpath='{.metadata.annotations.watchdog\.last-restart-ts}' 2>/dev/null)

# If it doesn't have the post-it yet, we assume 0
if ! echo "$LAST_RESTART" | grep -Eq '^[0-9]+$'; then
  LAST_RESTART=0
fi

AGE=$(( NOW - LAST_RESTART ))

if [ "$AGE" -lt "$COOLDOWN_SEC" ]; then
  echo "[watchdog] COOLDOWN ACTIVE: Calico was restarted $AGE secs ago. $(( COOLDOWN_SEC - AGE )) secs remaining before allowing another restart."
  exit 0
fi

# ---- Step B: Search for RECENT events -----------------------------
kubectl get events --all-namespaces --field-selector type=Warning \
  -o go-template='{{range .items}}{{.lastTimestamp}}|{{.message}}{{"\n"}}{{end}}' \
  | grep 'plugin type="calico" failed' \
  | grep 'Unauthorized' > /tmp/eventos_calico.txt || true

FAILURES=0
while IFS='|' read -r TS _MSG; do
  [ -z "$TS" ] && continue
  TS_SEC=$(date -d "$TS" +%s 2>/dev/null) || continue
  EV_AGE=$(( NOW - TS_SEC ))

  if [ "$EV_AGE" -le "$EVENT_WINDOW_SEC" ]; then
    FAILURES=$((FAILURES + 1))
  fi
done < /tmp/eventos_calico.txt

# ---- Step C: Action (Restart and stick the new Post-it) ---------
if [ "$FAILURES" -gt 0 ]; then
  echo "[watchdog] ALERT: $FAILURES authentication loss events detected in the last 15 min."

  if [ "$DRY_RUN" = "1" ]; then
    echo "[watchdog] DRY_RUN=1 -> calico-node will NOT be restarted (test mode)."
  else
    echo "[watchdog] Restarting calico-node DaemonSet..."
    kubectl rollout restart daemonset/calico-node -n kube-system

    # We stick the post-it to Calico with the exact current time
    kubectl annotate ds calico-node -n kube-system watchdog.last-restart-ts="$NOW" --overwrite

    echo "[watchdog] Command executed. Watchdog blocked for 1 HOUR (3600s)."
  fi
else
  echo "[watchdog] Network operating normally."
fi
