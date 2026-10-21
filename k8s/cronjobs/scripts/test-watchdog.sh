#!/usr/bin/env bash
# test-watchdog.sh — test suite for the Calico watchdog CronJob.
#
# Verifies that the watchdog acts ONLY when every condition holds
# (signature "plugin type=calico failed" + "Unauthorized" + recent event + no
# cooldown), each condition tested individually, combined and complete.
# Every case triggers a one-off Job from the CronJob and self-evaluates PASS/FAIL
# by reading its logs. Nothing is ever restarted: cases abort unless DRY_RUN=1.
#
# Usage (from the repo root, with the CronJobs applied: make cronjobs):
#   k8s/cronjobs/scripts/test-watchdog.sh prepare     # DRY_RUN=1 + save cooldown annotation
#   k8s/cronjobs/scripts/test-watchdog.sh all         # case1..case6 + rbac
#   k8s/cronjobs/scripts/test-watchdog.sh finish      # cleanup + DRY_RUN=0 (armed) + restore annotation
#
# Individual cases:
#   case1  baseline, no events                          -> no action
#   case2  calico signature WITHOUT "Unauthorized"      -> no action
#   case3  "Unauthorized" WITHOUT calico signature      -> no action
#   case4  full signature but 30 min old                -> no action (anti-loop window)
#   case5  full signature, recent, no cooldown          -> ALERT (DRY_RUN: no restart)
#   case6  full signature + recent restart annotation   -> COOLDOWN blocks it
#   rbac   3 permissions that must be "yes", 3 that must be "no"
#
# Env: KUBECTL (default "microk8s kubectl"), AIRFLOW_NAMESPACE (default airflow).
# Run it in a quiet window: REAL Calico errors in the last 15 min would alter results.
set -uo pipefail

KUBECTL="${KUBECTL:-microk8s kubectl}"
AIRFLOW_NS="${AIRFLOW_NAMESPACE:-airflow}"
NS=kube-system
CRON=calico-watchdog-cron
DS=calico-node
ANN=watchdog.last-restart-ts
SAVED_ANN=watchdog.test-saved-ts
PREFIX=test-watchdog
PASS=0
FAIL=0

k() {
    # shellcheck disable=SC2086  # KUBECTL is intentionally word-split
    $KUBECTL "$@"
}

result() {  # result <PASS|FAIL> <message>
    if [ "$1" = PASS ]; then PASS=$((PASS + 1)); echo "  [PASS] $2"; else FAIL=$((FAIL + 1)); echo "  [FAIL] $2"; fi
}

dry_run_value() {
    k get cronjob "$CRON" -n "$NS" \
        -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].env[?(@.name=="DRY_RUN")].value}'
}

require_dry_run() {
    if [ "$(dry_run_value)" != "1" ]; then
        echo "ABORT: the CronJob is ARMED (DRY_RUN!=1). Run '$0 prepare' first." >&2
        exit 2
    fi
}

set_annotation() {  # set_annotation <epoch seconds>
    k annotate ds "$DS" -n "$NS" "$ANN=$1" --overwrite >/dev/null
}

inject_event() {  # inject_event <name> <message> <timestamp UTC ISO>
    k create -f - >/dev/null <<EOF
apiVersion: v1
kind: Event
metadata:
  name: $PREFIX-$1
  namespace: default
type: Warning
reason: FailedCreatePodSandBox
message: '$2'
involvedObject:
  kind: Pod
  name: fake-pod
  namespace: default
firstTimestamp: "$3"
lastTimestamp: "$3"
source:
  component: kubelet
EOF
}

delete_test_events() {
    k get events -n default -o name 2>/dev/null | grep "$PREFIX" | while read -r e; do
        k delete "$e" -n default >/dev/null 2>&1
    done
}

run_watchdog() {  # run_watchdog <case> -> prints the job logs
    local job
    job="$PREFIX-$1-$(date +%s)"
    k create job --from=cronjob/"$CRON" "$job" -n "$NS" >/dev/null
    k wait --for=condition=complete "job/$job" -n "$NS" --timeout=180s >/dev/null 2>&1 || true
    k logs "job/$job" -n "$NS" 2>/dev/null
    k delete job "$job" -n "$NS" --wait=false >/dev/null 2>&1 || true
}

expect_log() {  # expect_log <case> <description> <grep pattern>
    local logs
    logs="$(run_watchdog "$1")"
    if grep -q "$3" <<<"$logs"; then  # no pipe: `echo | grep -q` + pipefail can SIGPIPE
        result PASS "$1: $2"
    else
        result FAIL "$1: $2 (expected /$3/). Logs:"
        # shellcheck disable=SC2001
        echo "$logs" | sed 's/^/        /'
    fi
    delete_test_events
}

now_utc()   { date -u +%FT%TZ; }
ago_utc()   { date -u -d "-$1 min" +%FT%TZ; }
SIGNATURE='Failed to create pod sandbox: plugin type="calico" failed (add): error getting ClusterInformation: connection is unauthorized: Unauthorized'

case1() { require_dry_run; set_annotation 0
    expect_log case1 "baseline without events -> normal" "operating normally"; }

case2() { require_dry_run; set_annotation 0
    inject_event c2 'Failed to create pod sandbox: plugin type="calico" failed (add): context deadline exceeded' "$(now_utc)"
    expect_log case2 "calico signature without Unauthorized -> normal" "operating normally"; }

case3() { require_dry_run; set_annotation 0
    inject_event c3 'Get "https://10.152.183.1:443/api": Unauthorized' "$(now_utc)"
    expect_log case3 "Unauthorized outside the CNI -> normal" "operating normally"; }

case4() { require_dry_run; set_annotation 0
    inject_event c4 "$SIGNATURE" "$(ago_utc 30)"
    expect_log case4 "full signature but 30 min old -> normal" "operating normally"; }

case5() { require_dry_run; set_annotation 0
    inject_event c5 "$SIGNATURE" "$(now_utc)"
    expect_log case5 "full + recent + no cooldown -> ALERT (dry run)" "DRY_RUN=1"; }

case6() { require_dry_run; set_annotation "$(date +%s)"
    inject_event c6 "$SIGNATURE" "$(now_utc)"
    expect_log case6 "valid event but recent restart -> COOLDOWN" "COOLDOWN ACTIVE"; }

can_i() {  # can_i <expected yes|no> <description> <verb> <resource> <namespace|--all-namespaces> <serviceaccount>
    local ns_flag=(-n "$5")
    [ "$5" = "--all-namespaces" ] && ns_flag=(--all-namespaces)
    local got
    got="$(k auth can-i "$3" "$4" "${ns_flag[@]}" --as="system:serviceaccount:$6" 2>/dev/null)"
    if [ "$got" = "$1" ]; then result PASS "rbac: $2 -> $got"; else result FAIL "rbac: $2 -> got '$got', expected '$1'"; fi
}

rbac() {
    can_i yes "watchdog can restart calico" patch daemonsets kube-system "kube-system:calico-watchdog"
    can_i yes "watchdog can read events cluster-wide" list events --all-namespaces "kube-system:calico-watchdog"
    can_i yes "cleaner can delete airflow pods" delete pods "$AIRFLOW_NS" "$AIRFLOW_NS:pod-cleaner"
    can_i no "watchdog cannot delete pods" delete pods kube-system "kube-system:calico-watchdog"
    can_i no "cleaner cannot delete kube-system pods" delete pods kube-system "$AIRFLOW_NS:pod-cleaner"
    can_i no "cleaner cannot touch daemonsets" patch daemonsets kube-system "$AIRFLOW_NS:pod-cleaner"
}

prepare() {
    k set env cronjob/"$CRON" -n "$NS" DRY_RUN=1 >/dev/null
    local current
    current="$(k get ds "$DS" -n "$NS" -o jsonpath="{.metadata.annotations.watchdog\.last-restart-ts}")"
    k annotate ds "$DS" -n "$NS" "$SAVED_ANN=${current:-none}" --overwrite >/dev/null
    echo "DRY_RUN=1 set; current cooldown annotation saved (${current:-none})."
}

finish() {
    delete_test_events
    k get jobs -n "$NS" -o name | grep "$PREFIX" | while read -r j; do k delete "$j" -n "$NS" >/dev/null 2>&1; done
    local saved
    saved="$(k get ds "$DS" -n "$NS" -o jsonpath="{.metadata.annotations.watchdog\.test-saved-ts}")"
    if [ -n "$saved" ] && [ "$saved" != "none" ]; then set_annotation "$saved"; else k annotate ds "$DS" -n "$NS" "$ANN-" >/dev/null 2>&1; fi
    k annotate ds "$DS" -n "$NS" "$SAVED_ANN-" >/dev/null 2>&1
    k set env cronjob/"$CRON" -n "$NS" DRY_RUN=0 >/dev/null
    echo "Cleaned up, annotation restored, watchdog ARMED again (DRY_RUN=0)."
}

summary() {
    echo
    echo "Result: $PASS PASS · $FAIL FAIL"
    [ "$FAIL" -eq 0 ]
}

case "${1:-}" in
    prepare) prepare ;;
    finish)  finish ;;
    case1|case2|case3|case4|case5|case6) "$1"; summary ;;
    rbac)    rbac; summary ;;
    all)     case1; case2; case3; case4; case5; case6; rbac; summary ;;
    *) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
