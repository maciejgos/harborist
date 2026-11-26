#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
experiment="$(pwd -P)/experiments/rust-verification"
image=harborist-rust-exercise-python:local

docker build -t "$image" .
docker run --rm --mount "type=bind,src=$experiment,dst=/experiment" -w /experiment \
    rust:1.100.0-alpine sh -ec 'rustup component add rustfmt; rustc --version; cargo fmt --check && cargo test --locked && cargo build --release --locked'
docker run --rm --network none --cpus 2 --mount "type=bind,src=$experiment,dst=/experiment,readonly" \
    --entrypoint /bin/sh "$image" \
    -ec 'uname -sm; python --version; python /experiment/foreground_test.py; python /experiment/saved_run_test.py; python /experiment/compare.py; python /experiment/foreground_benchmark.py "$2"; python /experiment/compare.py "$1"' \
    sh "${1:-60}" "${2:-20}"
