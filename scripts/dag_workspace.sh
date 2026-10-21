#!/usr/bin/env bash
# dag_workspace.sh — print every path of a DAG plus quick navigation commands.
#
# Usage: scripts/dag_workspace.sh <dag_id>
set -euo pipefail
# shellcheck source=lib/common.sh
. "$(dirname "$0")/lib/common.sh"

[ $# -eq 1 ] || die "Uso: $0 <dag_id>"
DAG_ID="$1"
DAG_DIR="$REPO_ROOT/dags/$DAG_ID"
FILES_DIR="$REPO_ROOT/files/$DAG_ID"
[ -d "$DAG_DIR" ] || die "No existe el DAG: $DAG_DIR"

ENV_NAME="$(grep -m1 -oE '/opt/conda/envs/[^/]+' "$DAG_DIR/_dag.py" 2>/dev/null | sed 's|.*/||' || true)"
SCHEDULE="$(grep -m1 -oE 'schedule=[^,]+' "$DAG_DIR/_dag.py" 2>/dev/null | cut -d= -f2- || true)"

cat <<EOF

======================================================
 WORKSPACE: $DAG_ID
======================================================
 DAG dir      : $DAG_DIR
 DAG file     : $DAG_DIR/_dag.py
 Scripts      : $DAG_DIR/scripts
 SQL          : $DAG_DIR/sql
 Files (data) : $FILES_DIR
 Environment  : ${ENV_NAME:-no detectado}
 Schedule     : ${SCHEDULE:-no detectado}

 cd $DAG_DIR
 cd $FILES_DIR
 python tools/check_dags.py $DAG_ID
======================================================
EOF
