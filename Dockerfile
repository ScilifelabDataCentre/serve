FROM python:3.8-alpine3.19 as builder

LABEL maintainer="serve@scilifelab.se"
WORKDIR /app

ARG DISABLE_EXTRAS=false

COPY pyproject.toml ./

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
    curl \
    && pip install --upgrade --no-cache-dir pip==23.3.2 \
    && curl -sSL https://install.python-poetry.org | python3 - \
    && /root/.local/bin/poetry self add poetry-plugin-export



# If build-args is set to DISABLE_EXTRA=true, then we skip all superfluous software
RUN if [ "$DISABLE_EXTRAS" = "true" ]; then \
    /root/.local/bin/poetry export -f requirements.txt --output requirements.txt; \
    else /root/.local/bin/poetry export --all-extras  -f requirements.txt --output requirements.txt; \
    fi

RUN pip install --no-cache-dir -r requirements.txt
RUN python3 -m pip install --no-cache-dir Pillow==10.2.0 --global-option="build_ext" --global-option="--disable-tiff" --global-option="--disable-freetype" --global-option="--disable-lcms" --global-option="--disable-webp" --global-option="--disable-webpmux" --global-option="--disable-imagequant" --global-option="--disable-xcb" 


FROM bitnami/kubectl:1.28.6 as kubectl
FROM alpine/helm:3.14.0 as helm
FROM python:3.8-alpine3.19 as runtime

ARG DISABLE_EXTRAS=false

RUN apk add --update --no-cache \
    sudo \
    bash \
    postgresql-client \
    libpq \
    jpeg-dev \
    openjpeg-dev \
    libpng-dev \
    && rm -rf /usr/local/lib/python3.8/site-packages/

COPY --from=builder /usr/local/lib/python3.8/site-packages/ /usr/local/lib/python3.8/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/
COPY --from=helm /usr/bin/helm /usr/local/bin/

# Set working directory
WORKDIR /app
COPY . /app/

# If build-args is set to DISABLE_EXTRA=true, delete all test files
RUN if [ "$DISABLE_EXTRAS" = "true" ]; then \
    rm -rf */tests cypress */tests.py pytest.ini cypress.config.js conftest.py docs */.github; \
    fi

ARG USER=serve
RUN adduser -D $USER \
        && echo "$USER ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/$USER \
        && chmod 0440 /etc/sudoers.d/$USER \
        && if [ ! -d "/app/media" ]; then mkdir -p /app/media; fi \
        && if [ ! -d "/app/charts/values" ]; then mkdir -p /app/charts/values; fi \
        && if [ ! -d "/app/sent_emails" ]; then mkdir -p /app/sent_emails; fi \
        && chown -R $USER /app/fixtures /app/media /app/charts /app/sent_emails /app/static \
        && chgrp -R $USER /app/fixtures /app/media /app/charts /app/sent_emails /app/static

USER $USER
