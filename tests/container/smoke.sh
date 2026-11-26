#!/usr/bin/env bash
set -euo pipefail

export HARBORIST_WEB_PORT="${HARBORIST_WEB_PORT:-18765}"
project="harborist-smoke-$$"
compose=(docker compose --project-name "$project")
base="http://127.0.0.1:$HARBORIST_WEB_PORT"

cleanup() {
    status=$?
    if [[ $status != 0 ]]; then
        "${compose[@]}" logs || true
    fi
    "${compose[@]}" down --volumes
    return "$status"
}
trap cleanup EXIT

wait_for_web() {
    for attempt in {1..30}; do
        if curl --silent --fail --max-time 2 "$base/api/health"; then
            return
        fi
        sleep 1
    done
    return 1
}

if [[ -z ${HARBORIST_IMAGE:-} ]]; then
    "${compose[@]}" build service
fi
"${compose[@]}" up --no-build --wait --wait-timeout 60
"${compose[@]}" exec -T service git --version
"${compose[@]}" exec -T service gh --version
credentials="$(printf 'protocol=https\nhost=github.com\n\n' |
    "${compose[@]}" exec -T -e GH_TOKEN=harborist-smoke-token -e GIT_TERMINAL_PROMPT=0 \
        service git credential fill)"
grep -qx 'password=harborist-smoke-token' <<< "$credentials"
wait_for_web
curl --silent --show-error --fail "$base/" | grep -F '<div id="root"></div>'
curl --silent --show-error --fail "$base/app.js" --output /dev/null
curl --silent --show-error --fail "$base/style.css" --output /dev/null
test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --header 'Host: unrelated.example' "$base/api/health")" = 403
test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --header 'Origin: http://unrelated.example' \
    --header 'X-Harborist-Workspace: 1' --json '{}' "$base/api/workspaces")" = 403
"${compose[@]}" exec -T service sh -ec 'mkdir -p "$GH_CONFIG_DIR"; touch "$GH_CONFIG_DIR/smoke-marker"'
"${compose[@]}" up --no-build --force-recreate --wait --wait-timeout 60
wait_for_web
"${compose[@]}" exec -T service sh -ec 'test -f "$GH_CONFIG_DIR/smoke-marker"'
"${compose[@]}" exec -T web sh -ec 'test ! -e /home/harborist/.harborist/github-cli'
