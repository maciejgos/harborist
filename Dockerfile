FROM ghcr.io/astral-sh/uv:0.11.20@sha256:eaa5f1a3305307aaf9e67fe2bbba1d85ebbb2d8a63bce23af21797bfafbe0f8b AS uv
FROM python:3.14-alpine3.23@sha256:f6a7dec95e6205059dccfcb07faca3ca38729ea35df01231caf1d127bacedec8 AS python

FROM python AS dependencies
WORKDIR /opt/harborist
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-python-downloads --no-build --no-cache

FROM rust:1.100.0-alpine AS rust-build
WORKDIR /checkout
COPY experiments/rust-verification/Cargo.toml experiments/rust-verification/Cargo.lock experiments/rust-verification/
COPY experiments/rust-verification/src experiments/rust-verification/src
COPY src/harborist/web/assets src/harborist/web/assets
RUN cargo build --manifest-path experiments/rust-verification/Cargo.toml --release --locked

FROM alpine:3.23 AS rust-runtime
RUN apk add --no-cache git ca-certificates \
    && addgroup -g 10001 harborist \
    && adduser -u 10001 -G harborist -D harborist \
    && install -d -m 0700 -o harborist -g harborist /home/harborist/.harborist /home/harborist/.harborist/control
COPY --from=rust-build /checkout/experiments/rust-verification/target/release/harborist-verify /usr/local/bin/harborist-verify
COPY src/harborist/playbooks /opt/harborist/src/harborist/playbooks
COPY src/harborist/skills /opt/harborist/src/harborist/skills
WORKDIR /home/harborist
USER 10001:10001
ENTRYPOINT ["harborist-verify"]
CMD ["service", "/home/harborist/.harborist/control"]

FROM python AS runtime
RUN apk upgrade --no-cache \
    && apk add --no-cache git \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip \
    && addgroup -g 10001 harborist \
    && adduser -u 10001 -G harborist -D harborist \
    && install -d -m 0700 -o harborist -g harborist /home/harborist/.harborist /home/harborist/.harborist/control
WORKDIR /opt/harborist
COPY --from=dependencies /opt/harborist/.venv .venv
COPY src/harborist src/harborist
ENV PATH="/opt/harborist/.venv/bin:${PATH}" \
    PYTHONPATH=/opt/harborist/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
ENTRYPOINT ["python", "-m", "harborist"]
CMD ["service", "serve"]
