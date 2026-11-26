#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
experiment="$(pwd -P)/experiments/rust-verification"
image=harborist-rust-exercise-python:local

./experiments/rust-verification/docker-check.sh
docker run --rm --network none --cpus 2 --mount "type=bind,src=$experiment,dst=/experiment,readonly" \
    --entrypoint /bin/sh "$image" \
    -ec 'uname -sm; python --version; python /experiment/foreground_benchmark.py "$2"; python /experiment/compare.py "$1"' \
    sh "${1:-60}" "${2:-20}"
