# Node 24.22.2 bookworm-slim, Linux arm64 platform manifest.
ARG BASE_IMAGE=node@sha256:e80dee4ed3709cf1f8004e34ecfb90df71b7eac8ba0d7d6222ba238a823d1eea
FROM ${BASE_IMAGE}
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv git procps \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
WORKDIR /workspace
