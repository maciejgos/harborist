#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
root="$(pwd -P)"
image=harborist-rust-exercise-python:local

docker build -t "$image" .
docker run --rm --mount "type=bind,src=$root,dst=/checkout" \
    -w /checkout/experiments/rust-verification rust:1.100.0-alpine \
    sh -ec 'rustup component add rustfmt; cargo fmt --check; cargo test --locked; cargo build --release --locked'
docker run --rm --network none --mount "type=bind,src=$root/experiments/rust-verification,dst=/experiment,readonly" \
    --entrypoint /bin/sh "$image" \
    -ec 'python /experiment/foreground_test.py; python /experiment/saved_run_test.py; python /experiment/control_test.py; python /experiment/apply_test.py; python /experiment/settings_test.py; python /experiment/workspace_test.py; python /experiment/github_test.py; python /experiment/publication_test.py; python /experiment/cancellation_test.py; python /experiment/rework_test.py; python /experiment/compare.py'
