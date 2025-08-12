FROM python:3.12.11-alpine3.22 AS builder

LABEL maintainer="serve@scilifelab.se"
WORKDIR /app

ARG DISABLE_EXTRAS=false

COPY pyproject.toml ./
COPY poetry.lock ./

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

# Install Poetry, change configs and install packages.
RUN curl -sSL https://install.python-poetry.org | POETRY_VERSION=2.0.0 python3 - \
    && /root/.local/bin/poetry self add poetry-plugin-export \
    && /root/.local/bin/poetry config virtualenvs.create false \
    && /root/.local/bin/poetry config installer.max-workers 10 \
    && if [ "$DISABLE_EXTRAS" = "true" ]; then \
        /root/.local/bin/poetry install -n -q --no-cache --only main --no-root; \
        else /root/.local/bin/poetry install -n -q --no-cache --all-extras --no-root; \
        fi

FROM bitnami/kubectl:1.32.4 AS kubectl
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

COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
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
