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
  service:
    environment:
      PATH: /home/harborist/.harborist/tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
YAML
compose build service
compose up --no-build -d --wait --wait-timeout 25
compose exec -T service harborist service status | grep -Fq '"stopping":false'
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
    build) if [ -f message.txt ]; then touch fixed; fi; printf 'hello from Compose\n' > message.txt; artifact=null ;;
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
test "$(compose exec -T service git -C /home/harborist/.harborist/repository show "$candidate:message.txt")" = "hello from Compose"
compose exec -T service git -C /home/harborist/.harborist/repository branch fixture-delivery
compose exec -T service git init -q /home/harborist/.harborist/other-repository
if compose exec -T service harborist apply "$run_id" --branch fixture-delivery \
    --repo /home/harborist/.harborist/other-repository; then
    printf 'Application unexpectedly accepted a different repository.\n' >&2
    exit 1
fi
applied=$(compose exec -T service harborist apply "$run_id" --branch fixture-delivery)
printf '%s\n' "$applied" | grep -Fq '"resulting_sha":"'"$candidate"'"'
test "$(compose exec -T service git -C /home/harborist/.harborist/repository rev-parse fixture-delivery)" = "$candidate"
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
compose exec -T service sh -eu <<'FIXTURE'
cd /home/harborist/.harborist/repository
printf '%s\n' '{"version":1,"checks":[{"id":"fix","command":"test -f fixed"}]}' > harborist.yaml
git add harborist.yaml
git commit -qm 'Require rework'
FIXTURE
queued=$(compose exec -T service harborist run file:/home/harborist/.harborist/issue.md \
    --repo /home/harborist/.harborist/repository --json)
rework_id=$(printf '%s\n' "$queued" | sed -n 's/.*"run_id":"\([0-9a-f-]*\)".*/\1/p')
test -n "$rework_id"
failed=$(compose exec -T service harborist status "$rework_id" --wait --interval 0.05 --json)
printf '%s\n' "$failed" | grep -Fq '"outcome":"TEST_FAILED"'
compose exec -T service harborist rework "$rework_id" --feedback 'Add fixed' --json
reworked=$(compose exec -T service harborist status "$rework_id" --wait --interval 0.05 --json)
printf '%s\n' "$reworked" | grep -Fq '"outcome":"VERIFIED"'
printf '%s\n' "$reworked" | grep -Fq '"attempt_number":1'
cancelled=$(compose exec -T service harborist cancel "$rework_id" --reason 'Compose test complete' --json)
printf '%s\n' "$cancelled" | grep -Fq '"reason":"Compose test complete"'
replacement=$(compose exec -T service harborist intake file:/home/harborist/.harborist/issue.md \
    --repo /home/harborist/.harborist/repository --ref 'HEAD^' --json)
replacement_id=$(printf '%s\n' "$replacement" | sed -n 's/.*"run_id":"\([0-9a-f-]*\)".*/\1/p')
test -n "$replacement_id"
retired=$(compose exec -T service harborist supersede "$saved_id" --replacement "$replacement_id" --reason 'Use the saved replacement')
printf '%s\n' "$retired" | grep -Fq '"replacement":"'"$replacement_id"'"'
test "$(compose exec -T service harborist supersede "$saved_id" --replacement "$replacement_id" --reason 'Use the saved replacement')" = "$retired"
status=$(compose exec -T service harborist status "$replacement_id" --wait --interval 0.05 --json)
printf '%s\n' "$status" | grep -Fq '"outcome":"VERIFIED"'
retired=$(compose exec -T service harborist supersede "$run_id" file:/home/harborist/.harborist/issue.md --ref 'HEAD^' --reason 'Use a freshly captured replacement')
replacement_id=$(printf '%s\n' "$retired" | sed -n 's/.*"replacement":"\([0-9a-f-]*\)".*/\1/p')
test -n "$replacement_id"
status=$(compose exec -T service harborist status "$replacement_id" --wait --interval 0.05 --json)
printf '%s\n' "$status" | grep -Fq '"outcome":"VERIFIED"'
custom=/home/harborist/.harborist/custom-runs
queued=$(compose exec -T service harborist run file:/home/harborist/.harborist/issue.md \
    --repo /home/harborist/.harborist/repository --ref 'HEAD^' --runs-dir "$custom" --json)
custom_id=$(printf '%s\n' "$queued" | sed -n 's/.*"run_id":"\([0-9a-f-]*\)".*/\1/p')
test -n "$custom_id"
status=$(compose exec -T service harborist status "$custom_id" --wait --interval 0.05 --json)
printf '%s\n' "$status" | grep -Fq '"outcome":"VERIFIED"'
retired=$(compose exec -T service harborist supersede "$custom_id" file:/home/harborist/.harborist/issue.md \
    --ref 'HEAD^' --runs-dir "$custom" --reason 'Keep the custom Run root')
replacement_id=$(printf '%s\n' "$retired" | sed -n 's/.*"replacement":"\([0-9a-f-]*\)".*/\1/p')
test -n "$replacement_id"
status=$(compose exec -T service harborist status "$replacement_id" --wait --interval 0.05 --json)
printf '%s\n' "$status" | grep -Fq '"runs_root":"'"$custom"'"'
printf '%s\n' "$status" | grep -Fq '"outcome":"VERIFIED"'
compose exec -T service test -f "$custom/$replacement_id/contract.json"
compose exec -T service sh -eu <<'FIXTURE'
cd /home/harborist/.harborist/repository
printf '%s\n' '{"version":1,"checks":[{"id":"drain","command":"touch /home/harborist/.harborist/drain-started && sleep 3 && test -f message.txt"}]}' > harborist.yaml
git add harborist.yaml
git commit -qm 'Hold TEST open during service stop'
FIXTURE
queued=$(compose exec -T service harborist run file:/home/harborist/.harborist/issue.md \
    --repo /home/harborist/.harborist/repository --json)
drain_id=$(printf '%s\n' "$queued" | sed -n 's/.*"run_id":"\([0-9a-f-]*\)".*/\1/p')
test -n "$drain_id"
compose exec -T service sh -ec '
    for attempt in $(seq 1 50); do
        test -f /home/harborist/.harborist/drain-started && exit 0
        sleep 0.1
    done
    exit 1
'
stopping=$(compose exec -T service harborist service stop)
printf '%s\n' "$stopping" | grep -Fq '"stopping":true'
compose wait service || { compose logs service >&2; exit 1; }
compose start --wait service
drained=$(compose exec -T service harborist status "$drain_id" --json)
printf '%s\n' "$drained" | grep -Fq '"state":"FINISHED"'
printf '%s\n' "$drained" | grep -Fq '"outcome":"VERIFIED"'
printf 'Rust Compose queued workflow reached VERIFIED and served its evidence.\n'
