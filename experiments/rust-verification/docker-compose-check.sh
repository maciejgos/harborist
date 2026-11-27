#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
project="harborist-rust-check-$(uuidgen | tr '[:upper:]' '[:lower:]')"
override=$(mktemp)
export HARBORIST_WEB_PORT="${HARBORIST_WEB_PORT:-18765}"
compose() {
    docker compose --project-name "$project" -f compose.rust.yaml -f "$override" "$@"
}
cleanup() {
    compose down --volumes >/dev/null 2>&1 || true
    rm -f "$override"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cat >"$override" <<'YAML'
services:
  worker:
    environment:
      PATH: /home/harborist/.harborist/tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
YAML
compose build service
compose up --no-build -d --wait --wait-timeout 25
compose exec -T service sh -eu <<'FIXTURE'
cd /home/harborist/.harborist
mkdir tools
cat >tools/codex <<'CODEX'
#!/bin/sh
set -eu
output=
while [ "$#" -gt 0 ]; do
    if [ "$1" = --output-last-message ]; then
        output=$2
        shift
    fi
    shift
done
request=$(cat)
stage=$(printf '%s' "$request" | sed -n 's/.*"stage":"\([a-z]*\)".*/\1/p')
case "$stage" in
    design) artifact='"AC-001: Write the requested file."' ;;
    plan) artifact='"Create message.txt."' ;;
    build) printf 'hello from Compose\n' > message.txt; artifact=null ;;
    review)
        test "$(cat message.txt)" = 'hello from Compose'
        identity=$(printf '%s' "$request" | sed -n 's/.*"candidate":\({[^}]*}\).*/\1/p')
        test -n "$identity"
        ;;
    *) exit 1 ;;
esac
if [ "$stage" = review ]; then
    printf '{"result":{"stage":"review","status":"ready","candidate":%s,"criteria":[{"criterion_id":"AC-001","status":"pass"}]},"artifact":"Approved.","plan_update":null,"process_report":null}\n' "$identity" >"$output"
else
    printf '{"result":{"stage":"%s","status":"ready"},"artifact":%s,"plan_update":null,"process_report":null}\n' "$stage" "$artifact" >"$output"
fi
CODEX
chmod 700 tools/codex
git init -q repository
git -C repository config user.name 'Harborist Compose Fixture'
git -C repository config user.email 'harborist@example.invalid'
printf '%s\n' '{"version":1,"checks":[{"id":"contents","command":"grep -qx \"hello from Compose\" message.txt"}]}' > repository/harborist.yaml
git -C repository add harborist.yaml
git -C repository commit -qm 'Freeze Compose fixture'
printf 'Write the requested file.\n' > issue.md
FIXTURE

origin="http://127.0.0.1:$HARBORIST_WEB_PORT"
request_id=$(uuidgen | tr '[:upper:]' '[:lower:]')
submitted=$(curl --fail-with-body --silent --show-error "$origin/api/workspace/runs" \
    -H "Origin: $origin" -H 'X-Harborist-Workspace: 1' -H 'Content-Type: application/json' \
    --data "{\"request_id\":\"$request_id\",\"source\":\"/home/harborist/.harborist/issue.md\",\"repository\":\"/home/harborist/.harborist/repository\"}")
run_id=$(printf '%s\n' "$submitted" | sed -n 's/.*"run_id":"\([0-9a-f-]*\)".*/\1/p')
test -n "$run_id"
for attempt in $(seq 1 25); do
    status=$(curl --fail-with-body --silent --show-error "$origin/api/runs/$run_id")
    if printf '%s' "$status" | grep -q '"state":"FINISHED"'; then
        break
    fi
    sleep 1
done
printf '%s\n' "$status" | grep -q '"outcome":"VERIFIED"'
report=$(curl --fail-with-body --silent --show-error "$origin/api/runs/$run_id/artifacts/report.md")
printf '%s\n' "$report" | grep -q VERIFIED
candidate=$(printf '%s\n' "$status" | sed -n 's/.*"candidate_sha":"\([0-9a-f]*\)".*/\1/p')
test -n "$candidate"
test "$(compose exec -T worker git -C /home/harborist/.harborist/repository show "$candidate:message.txt")" = "hello from Compose"
captured=$(compose exec -T service harborist intake file:/home/harborist/.harborist/issue.md \
    --repo /home/harborist/.harborist/repository --json)
saved_id=$(printf '%s\n' "$captured" | sed -n 's/.*"run_id":"\([0-9a-f-]*\)".*/\1/p')
test -n "$saved_id"
created=$(compose exec -T service harborist status "$saved_id" --json)
printf '%s\n' "$created" | grep -Fq '"lifecycle":"CREATED"'
listing=$(compose exec -T service harborist runs --json)
printf '%s\n' "$listing" | grep -Fq '"run_id":"'"$saved_id"'"'
queued=$(compose exec -T service harborist run "$saved_id" --json)
printf '%s\n' "$queued" | grep -Fq '"run_id":"'"$saved_id"'"'
status=$(compose exec -T service harborist status "$saved_id" --wait --interval 0.05 --json)
printf '%s\n' "$status" | grep -q '"outcome":"VERIFIED"'
printf 'Rust Compose queued workflow reached VERIFIED and served its evidence.\n'
