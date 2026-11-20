ARG PYTHON_IMAGE=python:3.14.9-alpine3.23
FROM ${PYTHON_IMAGE} AS builder

LABEL maintainer="serve@scilifelab.se"
WORKDIR /app

ARG DISABLE_EXTRAS=false
ARG ENABLE_PROFILING=false

COPY pyproject.toml ./
COPY poetry.lock ./

RUN apk upgrade --no-cache \
    && apk add --no-cache \
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

# Keep application packages separate from Poetry and the base image's packaging tools.
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | POETRY_VERSION=2.1.3 python3 - \
    && python3 -m venv --without-pip /opt/venv \
    && /root/.local/bin/poetry config virtualenvs.create false \
    && /root/.local/bin/poetry config installer.max-workers 10 \
    && if [ "$DISABLE_EXTRAS" = "true" ]; then \
        /root/.local/bin/poetry install -n --no-cache --only main --no-root; \
        elif [ "$ENABLE_PROFILING" = "true" ]; then \
            /root/.local/bin/poetry install -n --no-cache --with profiling --no-root; \
        else /root/.local/bin/poetry install -n --no-cache --all-extras --no-root; \
        fi

# Download official Helm and kubectl releases and verify their checksums.
FROM --platform=$BUILDPLATFORM alpine:3.23 AS tools

ARG TARGETARCH
ARG KUBECTL_VERSION=1.35.10
ARG HELM_VERSION=3.22.1

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates curl \
    && mkdir -p /tools \
    && curl -fsSL --retry 3 -o /tools/kubectl \
        "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && curl -fsSL --retry 3 -o /tmp/kubectl.sha256 \
        "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl.sha256" \
    && echo "$(cat /tmp/kubectl.sha256)  /tools/kubectl" | sha256sum -c - \
    && curl -fsSL --retry 3 -o /tmp/helm.tar.gz \
        "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${TARGETARCH}.tar.gz" \
    && curl -fsSL --retry 3 -o /tmp/helm.sha256 \
        "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${TARGETARCH}.tar.gz.sha256sum" \
    && echo "$(cut -d ' ' -f 1 /tmp/helm.sha256)  /tmp/helm.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/helm.tar.gz --strip-components=1 -C /tools "linux-${TARGETARCH}/helm" \
    && chmod 0755 /tools/kubectl /tools/helm

FROM ${PYTHON_IMAGE} AS runtime

ARG DISABLE_EXTRAS=false

RUN apk upgrade --no-cache \
    && apk add --no-cache \
    sudo \
    bash \
    postgresql-client \
    libpq \
    libjpeg-turbo \
    openjpeg \
    libpng \
    && python3 -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv
COPY --from=tools /tools/kubectl /tools/helm /usr/local/bin/

# Set working directory
WORKDIR /app
COPY . /app/

ARG USER=serve


# Remove test files when DISABLE_EXTRAS=true.
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
