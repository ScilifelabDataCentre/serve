# Agent guide — SciLifeLab Serve

This document summarizes how this repository is organized and how to work on it safely. It is derived from the codebase and tooling configuration, not from private operational runbooks.

## What this project is

**SciLifeLab Serve** is the main **Django** web application for [SciLifeLab Serve](https://serve.scilifelab.se): ML model serving, hosted apps (e.g. Shiny, Streamlit, Dash), notebooks, and related tooling for researchers. The app orchestrates work against a **Kubernetes** cluster via cluster configuration (e.g. `cluster.conf`); many flows need a real or local cluster, not only the HTTP UI.

- **Django project package:** `studio` (`DJANGO_SETTINGS_MODULE` / `studio.settings`, see `manage.py`, `pytest.ini`).
- **Primary URL routing:** `studio/urls.py` — includes `common`, `portal`, `projects`, `models`, `apps`, `api`, `doi_minting`, wiki/docs, OpenAPI, and admin.

## Runtime stack (from `Dockerfile`, `docker-compose.yaml`, `pyproject.toml`)

| Layer | Technology |
| --- | --- |
| Python | 3.12.x (container base matches `Dockerfile`; Poetry allows `^3.10` but image pins 3.12) |
| Web | Django 5.1.x, Gunicorn/Uvicorn via app scripts |
| DB | PostgreSQL 17 (`db` service) |
| Async work | Celery (`celery-worker`, `celery-beat`), RabbitMQ, Redis |
| Package manager | Poetry (`pyproject.toml`, `poetry.lock`) |
| E2E UI tests | Cypress (`package.json`, `cypress.config.js`, `Dockerfile.cypress`) |

Compose services include `studio` (main app), `db`, `redis`, `rabbit`, Celery, `event-listener`, and test helpers (`unit-tests`, `ui-tests` use profiles — see below).

## Repository layout (high level)

| Path | Role |
| --- | --- |
| `studio/` | Django project: `settings.py`, `urls.py`, WSGI/ASGI, middleware |
| `api/` | REST/OpenAPI (`api/openapi/`, versioned routes under `/api/` and `/openapi/`) |
| `apps/` | Project-scoped “apps” (hosted apps, metadata, etc.) |
| `projects/` | Projects, permissions, project-level behavior |
| `models/` | ML/model-related Django app |
| `portal/` | Portal UI and routes |
| `common/` | Shared utilities, URLs, cross-cutting concerns |
| `doi_minting/` | DOI minting integration |
| `monitor/` | Monitoring-related code |
| `fixtures/` | JSON fixtures for DB seeding / tests |
| `templates/`, `static/` | Django templates and static assets |
| `scripts/` | Shell entrypoints (e.g. `run_web.sh`, `run_worker.sh`, `wait-for-it.sh`) |
| `cypress/` | Cypress specs and fixtures |
| `docs/`, `ADRs/` | Documentation and architecture decision records |
| `.github/workflows/` | CI, pre-commit, E2E, publish, pa11y |

## Installed Django apps (core product)

`studio/settings.py` registers, among others: `common`, `portal`, `projects`, `models`, `apps`, `api`, `doi_minting`, plus standard Django, DRF, Celery beat, guardian, waffle, axes, HTMX, django-wiki stack, etc. New features usually belong in one of these apps or a new app added to `INSTALLED_APPS` and wired in `studio/urls.py`.

## Local development (typical)

1. Copy `.env.template` → `.env` and adjust variables (see `README.md` for cluster, `AUTH_DOMAIN`, nip.io notes).
2. Provide `cluster.conf` when Kubernetes-backed features are required.
3. Build/run with Docker Compose (see `README.md` for BuildKit/SSH when building private deps).

Default local URL pattern from docs: `http://studio.127.0.0.1.nip.io:8080` — avoid bare `localhost` for ingress-dependent features.

## Testing

### Python / Django (pytest)

- **Config:** `pytest.ini` sets `DJANGO_SETTINGS_MODULE = studio.settings` and defines the `integration` marker for tests that hit external resources.
- **Root fixtures:** `conftest.py` applies `override_settings(INACTIVE_USERS=False, AXES_ENABLED=False)` for the session.
- **Default CI command:** `docker compose run unit-tests` runs `pytest -n auto -m "not integration"` (see `docker-compose.yaml` `unit-tests` service).
- **Coverage:** `addopts` in `pytest.ini` enables `--cov=.`; omit patterns in `pyproject.toml` `[tool.coverage]`.

To run integration-marked tests locally, adjust the `unit-tests` command in `docker-compose.yaml` to drop `-m "not integration"` (as documented in `README.md`).

### Cypress

- **Config:** `cypress.config.js`; dev deps in root `package.json`.
- **Scripts:** `npm run cy:run`, `npm run cy:run:parallel` (parallel targets `cypress/e2e/ui-tests`).
- E2E expects the app reachable at the configured `baseUrl`; integration suites may need Django test endpoints enabled in config (see `README.md`).

## Code quality (match repo tooling)

| Tool | Source of truth |
| --- | --- |
| **Black** | Line length **120**, `pyproject.toml` `[tool.black]` |
| **isort** | Profile **black**, `pyproject.toml` `[tool.isort]` |
| **Flake8** | `.flake8` (max line 120; excludes include migrations, `models/`, etc.) |
| **mypy** | `pyproject.toml` `[tool.mypy]` — strict for `studio.*`; many packages relaxed or `ignore_errors` while typing is rolled out |
| **Pre-commit** | `.pre-commit-config.yaml` — black, isort, flake8, mypy, plus generic hooks (JSON/YAML, secrets, EOF, etc.) |

Run locally: `pre-commit run --all-files` (CI runs this on PRs/pushes to `develop`).

**Note:** Pre-commit notes in `pyproject.toml` that `pre-commit run --all-files` may not fully respect every `pyproject.toml` linter setting; hooks carry their own excludes where needed.

## Continuous integration (`.github/workflows`)

- **`ci.yaml`:** Docker Compose up/build, health check against `STUDIO_URL`, then `docker compose run unit-tests`.
- **`pre-commit.yaml`:** Python 3.12, `pre-commit run --all-files`.
- **`e2e-tests.yaml`**, **`pa11y-test.yaml`**, **`publish.yaml`:** See workflow files for triggers and steps.

CI is configured for the upstream repo name `scilifelabdatacentre/serve` (job guards may skip forks).

## Git workflow (from `README.md`)

- **`main`:** production-aligned code.
- **`develop` / `staging`:** development stages; contributions and PRs typically target **`develop`**.

## Pointers for changes

- **New HTTP routes:** `studio/urls.py` and the relevant app’s `urls.py`.
- **REST API:** `api/` and `api/openapi/`; namespaces include `api`, `api-v1`, OpenAPI namespaces.
- **Background work:** Celery tasks under app modules (see `apps/background_tasks/README.md` for one area).
- **Environment-specific behavior:** Prefer `studio/settings.py` and env vars; avoid hardcoding secrets (use `.env` / deployment secrets).

For human-oriented setup and Kubernetes/Rancher details, start with `README.md` and `docs/adr/`.
