# Builder and runtime tags should match
FROM ghcr.io/astral-sh/uv:0.8-python3.12-alpine AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image; see `standalone.Dockerfile`
# for an example.
ENV UV_PYTHON_DOWNLOADS=0

RUN apk add --update --no-cache \
    build-base \
    python3-dev \
    postgresql-dev \
    libpq \
    tiff-dev \
    jpeg-dev \
    openjpeg-dev \
    zlib-dev \
    freetype-dev \
    lcms2-dev \
    libwebp-dev \
    tcl-dev \
    tk-dev \
    harfbuzz-dev \
    fribidi-dev \
    libimagequant-dev \
    libxcb-dev libpng-dev \
    gcc \
    libffi-dev \
    musl-dev \
    curl

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM bitnami/kubectl:1.31.4 AS kubectl
FROM alpine/helm:3.18.3 AS helm
FROM python:3.12.11-alpine3.22 AS runtime

ARG DISABLE_EXTRAS=false

RUN apk add --update --no-cache \
    sudo \
    bash \
    postgresql-client \
    libpq \
    jpeg-dev \
    openjpeg-dev \
    libpng-dev \
    && rm -rf /usr/local/lib/python3.12/site-packages/

COPY --from=builder --chown=app:app /app /app
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/
COPY --from=helm /usr/bin/helm /usr/local/bin/

# Set working directory
WORKDIR /app
COPY . /app/

ARG USER=serve


# If build-args is set to DISABLE_EXTRA=true, delete all test files
RUN if [ "$DISABLE_EXTRAS" = "true" ]; then \
        rm -rf */tests cypress */tests.py pytest.ini cypress.config.js conftest.py docs */.github; \
    fi \
    && adduser -D $USER \
    && echo "$USER ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/$USER \
    && chmod 0440 /etc/sudoers.d/$USER \
    && if [ ! -d "/app/media" ]; then mkdir -p /app/media; fi \
    && if [ ! -d "/app/charts/values" ]; then mkdir -p /app/charts/values; fi \
    && if [ ! -d "/app/sent_emails" ]; then mkdir -p /app/sent_emails; fi \
    && chown -R $USER /app/fixtures /app/media /app/charts /app/sent_emails /app/static \
    && chgrp -R $USER /app/fixtures /app/media /app/charts /app/sent_emails /app/static

USER $USER

