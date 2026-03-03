# ADR-0001: Separate Invenio API client from Serve metadata preparation

- **Status**: Accepted (retroactive)
- **Date written**: 2026-03-03
- **Decision date**: earlier (retroactively documented; exact date unknown)
- **Decision drivers**: maintainability, clear boundaries, testability, reuse, reduced coupling

## Context

Serve integrates with InvenioRDM for creating/versioning records and reserving/minting DOIs for application instances.

As of the date this ADR was written, the Invenio-related code lives in two “kinds” of places:

- **Pure Invenio API communication (client)**: `doi_minting/clients/invenio_client/`
  - Example: `doi_minting/clients/invenio_client/invenio_client.py`
  - Characteristics:
    - Focused on HTTP/session/TLS, endpoint paths, request/response handling.
    - Should not know about Serve’s Django models, registry, waffle switches, or other Serve-specific structures.
    - This code is intentionally generic and reusable.

- **Serve-side preparation + orchestration (metadata prep / DOI workflow)**: currently split across `doi_minting/services/invenio_svc.py` and integration call sites in `apps/`
  - Example responsibilities currently in `InvenioService`:
    - Building Invenio metadata from Serve’s ORM models (`generate_invenio_metadata`, `model_to_dict`, `User` lookup).
    - Serve-specific eligibility checks (e.g. access == public; version/image checks).
    - End-to-end workflow orchestration (create draft → reserve DOI → publish → persist `invenio_record_id` and `app_doi`).
    - Integration with Serve registry (`apps.app_registry.APP_REGISTRY`).
  - Example responsibilities currently in `apps/helpers.py` / background task wiring:
    - Collecting additional metadata from forms (e.g. `language`, `tags/subjects`) to pass into DOI provisioning.
    - Deciding sync vs async execution via waffle switches (direct call vs background task).
    - Triggering DOI provisioning via `apps/background_tasks/tasks/doi_provisioning.py` or directly calling `save_metadata_to_invenio_then_mint_doi`.

This mixing makes it harder to reason about responsibilities and encourages accidental coupling between the “generic client” and Serve-specific concepts.

## Decision

This ADR **retroactively documents** an already-made decision to separate Invenio-related code into two distinct layers with explicit boundaries:

1. **Keep the existing “pure client” layer**:
   - `doi_minting/clients/invenio_client/` remains the home of InvenioRDM API communication code.
   - This package must remain **Serve-agnostic** (no imports from Serve’s apps/models/registry; no Django dependencies).
   - Dependency direction: **Serve code may depend on the client**, but the client must not depend on Serve.

2. **Have a dedicated Serve-side “metadata preparation” module/app** for DOI/Invenio prep work:
   - The intended structure is a top-level module (Django app or pure package), e.g.:
     - `app_metadata_prep/` (preferred name in discussions), or
     - `doi_metadata_prep/` (if we want the name to reflect DOI scope).
   - Serve-specific responsibilities belong in this area (even if some are currently still located in `doi_minting/services/invenio_svc.py`), including:
     - Building/validating Invenio payloads from Serve models.
     - Eligibility checks and Serve policies.
     - Workflow orchestration and persistence back into Serve models.

`doi_minting/` is intended to be a **thin integration shell** (URLs/views, toggles, and any backwards-compatible entrypoints) that delegates to the metadata-prep layer and the existing Invenio client.

## Implementation status (as of 2026-03-03)

- **Already matches the decision**:
  - The pure client layer exists and is isolated at `doi_minting/clients/invenio_client/`.

- **Still in progress / remaining work**:
  - Serve-specific metadata preparation + workflow orchestration is still implemented across:
    - `doi_minting/services/invenio_svc.py` (metadata generation + Invenio workflow), and
    - `apps/helpers.py` / `apps/background_tasks/tasks/doi_provisioning.py` (form-derived metadata collection and execution wiring),
    and should be consolidated into the dedicated metadata-prep module/app (e.g. `app_metadata_prep/`) so call sites stay thin.

## Options considered

### Option A (chosen): Keep `invenio_client` and create `app_metadata_prep`
- **Pros**:
  - Clear, enforceable boundaries (client vs Serve prep).
  - Easier unit testing (client tests stay pure; prep can be tested with Django fixtures).
  - Enables reuse of `invenio_client` in other contexts without Serve dependencies.
  - Reduces pressure to cram “mapping logic” into the client.
- **Cons**:
  - Requires a refactor/move of code and imports.
  - Requires deciding API boundaries and naming.

### Option B: Keep everything under `doi_minting/`
- **Pros**:
  - Lowest churn.
- **Cons**:
  - Continues conflating “DOI product integration” with “Invenio HTTP client.”
  - Increases coupling; makes it harder to keep the client Serve-agnostic over time.

### Option C: Move `invenio_client` out to its own repository/package
- **Pros**:
  - Strong separation and reuse.
- **Cons**:
  - Packaging/release overhead not justified yet.
  - More complex dependency management for Serve.

## Consequences

- **Positive**:
  - The Invenio client remains stable, reusable, and easy to review.
  - Serve-specific metadata logic has a dedicated home and can evolve independently.
  - Cleaner mental model: “prep produces payloads + decisions; client executes HTTP.”

- **Negative / costs**:
  - A migration period where call sites need updating.
  - Some functions may need new interfaces (e.g., passing `app_instance` vs passing “prepared record request” objects).

## Implementation sketch (non-binding)

- **Keep**:
  - `doi_minting/clients/invenio_client/**`

- **Move from** `doi_minting/services/invenio_svc.py` **to** `app_metadata_prep/**`:
  - Eligibility and policy checks (`is_app_eligible_for_doi`, image/version logic).
  - Metadata creation (`generate_invenio_metadata` and its helper methods).
  - Workflow orchestration (`process_app_metadata`, persistence back to app instance).

- **Leave in / rewire** `doi_minting/`:
  - Any URLs/views (e.g., keyword search endpoint).
  - Backwards-compatible entrypoint functions (e.g., keep `save_metadata_to_invenio_then_mint_doi` as a delegating wrapper during transition).

## Notes / scope boundaries

- This ADR intentionally does **not** decide:
  - The final public API between `doi_minting`, `app_metadata_prep`, and the client.
  - The final naming of the new module (only the intent and separation).
  - Whether the new module must be a Django app vs a pure Python package (either is acceptable as long as the boundary is respected).
