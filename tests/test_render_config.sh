#!/usr/bin/env bash
# Renders the templates with the example env and checks no ${VAR} is left.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp "$ROOT/config/platform.env.example" "$TMP/platform.env"
sed -i 's|^SERVER_IP=.*|SERVER_IP="10.0.0.10"|' "$TMP/platform.env"
ENV_FILE="$TMP/platform.env" VALUES_OUT="$TMP/values.yaml" POD_TEMPLATE_OUT="$TMP/pod_template.yaml" \
    "$ROOT/scripts/render_config.sh" >/dev/null
for f in "$TMP/values.yaml" "$TMP/pod_template.yaml"; do
    # shellcheck disable=SC2016  # searching for a literal ${
    if grep -n '\${' "$f"; then echo "Unrendered variable in $f"; exit 1; fi
done
grep -q 'WEBSERVER_SECRET_KEY=".\+"' "$TMP/platform.env" || { echo "secret key not persisted"; exit 1; }
python3 -c "import sys,yaml; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" "$TMP/values.yaml" "$TMP/pod_template.yaml"
[ -n "${KEEP_RENDERED:-}" ] && cp "$TMP/values.yaml" "$TMP/pod_template.yaml" "$KEEP_RENDERED"/
echo "render OK"
