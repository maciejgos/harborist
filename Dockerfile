FROM ghcr.io/astral-sh/uv:0.11.20@sha256:eaa5f1a3305307aaf9e67fe2bbba1d85ebbb2d8a63bce23af21797bfafbe0f8b AS uv
FROM python:3.14-alpine3.23@sha256:f6a7dec95e6205059dccfcb07faca3ca38729ea35df01231caf1d127bacedec8 AS python

FROM python AS dependencies
WORKDIR /opt/shipyard
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-python-downloads --no-build --no-cache

FROM python AS runtime
RUN apk upgrade --no-cache \
    && apk add --no-cache git \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip \
    && addgroup -g 10001 shipyard \
    && adduser -u 10001 -G shipyard -D shipyard \
    && install -d -m 0700 -o shipyard -g shipyard /home/shipyard/.shipyard /home/shipyard/.shipyard/control
WORKDIR /opt/shipyard
COPY --from=dependencies /opt/shipyard/.venv .venv
COPY src/shipyard src/shipyard
ENV PATH="/opt/shipyard/.venv/bin:${PATH}" \
    PYTHONPATH=/opt/shipyard/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
ENTRYPOINT ["python", "-m", "shipyard"]
CMD ["service", "serve"]
