# Backend (Polaris RFP) — Current Structure & How to Extend

This doc describes the **current** backend after the pruning/flattening work:

- **FastAPI modular HTTP surface** lives in `backend/app/routers/` (kept separate on purpose).
- **Business/pipeline logic** lives in `backend/app/pipeline/` plus a few top-level “orchestration” modules.
- **Persistence** is a single flat set of DynamoDB repositories in `backend/app/repositories/`.
- **Workflow** (stage + task seeding) is centralized and reused everywhere.

If you’re trying to orient yourself quickly, start with:

- `backend/app/main.py` (app wiring, routers, middleware)
- `backend/app/routers/rfp.py` (core entrypoints)
- `backend/app/repositories/rfp_rfps_repo.py` (RFP persistence)
- `backend/app/workflow.py` + `backend/app/stage_machine.py` (pipeline stage + sync)

---

## Overview (what this backend does)

The backend supports the core Polaris workflow:

1. **Find / ingest RFP** (upload PDF, analyze, store)
2. **Review (bid/no-bid)**
3. **Generate proposal**
4. **Submit**
5. **Contracting**
6. **Project handoff (lightweight placeholders for now)**

Along the way, **workflow tasks** are created/seeded to drive the pipeline.

Integrations are intentionally pragmatic:

- **Slack**: slash commands + interactions + events (signature-authenticated endpoints)
- **Google Drive**: minimal upload endpoint for proposal export
- **Canva**: OAuth + export/autofill workflows
- **GitHub**: API helpers for integration status / future automation

---

## Directory layout (separation of concerns)

All backend code lives under `backend/app/`.

### `app/main.py` (composition root)

`create_app()` builds the FastAPI application:

- Middleware setup (auth, logging, CORS, request-id)
- Exception handlers (RFC7807 problem responses)
- Router registration

This is the **only** place that should “know everything exists”.

### `app/routers/` (HTTP API surface)

One file per route group, thin controllers:

- Parse/validate inputs
- Call repository + service/pipeline functions
- Return stable JSON shapes used by the frontend

Avoid putting heavy logic here; if it grows, push it into `pipeline/`, `repositories/`, or `workflow.py`.

### `app/repositories/` (persistence adapters — flat)

These are DynamoDB access modules. They own:

- Storage keys (`pk`/`sk` patterns)
- Conditional writes / optimistic concurrency (where used)
- Pagination / GSI queries
- “normalize_for_api(...)” shaping (when needed)

**Naming convention:** `<area>_<thing>_repo.py` (e.g. `rfp_rfps_repo.py`, `workflows_tasks_repo.py`).

### `app/pipeline/` (domain workflow steps)

Pipeline modules are the “business logic” helpers used by routers/workers:

- `pipeline/intake/` — analyze RFP PDFs/URLs (`rfp_analyzer.py`)
- `pipeline/proposal_generation/` — proposal generation helpers and templates
- `pipeline/contracting/` — contract/budget doc generation helpers and queueing
- `pipeline/search/` — finder/scrapers

Pipeline code is allowed to call repos and integrations, but should stay **deterministic** where possible.

### `app/workflow.py` + `app/stage_machine.py` (canonical pipeline workflow)

This is the “single source of truth” for pipeline stage and task seeding:

- `compute_stage(...)` in `stage_machine.py` derives a stage from `(rfp, proposals)`
- `sync_for_rfp(...)` in `workflow.py`:
  - computes stage
  - ensures Opportunity exists
  - patches `OpportunityState.stage` (best-effort legacy state)
  - seeds tasks for that stage

Any time a router changes an RFP or proposal in a way that could change pipeline stage, it should call `sync_for_rfp(...)`.

### `app/opportunities.py` (single Opportunity record)

The system uses a single **Opportunity** row as the “hub” record:

- DynamoDB key: `pk = OPPORTUNITY#<id>`, `sk = PROFILE`
- Back-compat convention: `opportunityId == rfpId` (so we avoid a migration)

The legacy durable artifact `OpportunityState` is separate:

- `pk = OPPORTUNITY#<rfpId>`, `sk = STATE#CURRENT` (stored by `rfp_opportunity_state_repo.py`)

### `app/infrastructure/` (integration adapters + shared utilities)

Concrete integration code and low-level helpers:

- `infrastructure/integrations/slack/*` — Slack signatures + posting messages
- `infrastructure/integrations/canva/*` — Canva OAuth + jobs
- `infrastructure/google_drive.py` — minimal Drive upload helper
- `infrastructure/github/*` — GitHub API helpers
- `infrastructure/aws_clients.py` — boto3 client factories (cached)
- `infrastructure/storage/*` — S3 + content library storage helpers

### `app/workers/` (background workers)

Small workers intended for cron/ECS scheduled tasks:

- `workers/outbox_worker.py` — dispatch outbox events (Slack notifications etc.)
- `workers/contracting_worker.py` — contracting job processor (doc/budget generation)

---

## Data model (high level)

### RFP
Primary record for ingestion and review. Stored via `repositories/rfp_rfps_repo.py`.

### Proposal
Linked to an RFP. Stored via `repositories/rfp_proposals_repo.py`.

### Opportunity (hub record)
The unifying record everything can key off of. Stored via `app/opportunities.py`.

### OpportunityState (durable “artifact” state)
Legacy durable state used by some Slack/agent-like flows. Stored via `repositories/rfp_opportunity_state_repo.py`.

### Tasks
Workflow tasks. Stored via `repositories/workflows_tasks_repo.py`.

### Outbox events
Durable “side effect queue” for Slack notifications etc. Stored via `repositories/outbox_repo.py` and processed by `workers/outbox_worker.py`.

---

## Auth model (how requests are authenticated)

The Auth middleware distinguishes:

- **API routes (`/api/*`)**: Cognito JWT Bearer auth (most endpoints)
- **Slack endpoints (`/api/integrations/slack/*`)**: Slack signature verification (public path)
- **Google Drive public endpoints (`/googledrive/*`)**: opaque token style endpoints used by frontend flows (see middleware for exact rules)

See `backend/app/middleware/auth.py`.

---

## Configuration (environment)

Configuration is centralized in:

- `backend/app/settings.py`

You’ll need typical values for:

- AWS region + DynamoDB table name (required for real persistence)
- Cognito config (for authenticated API routes)
- Slack signing secret + bot token (for Slack webhooks/commands)
- Canva OAuth creds (for Canva integration routes)
- Google Drive credentials (if you use Drive upload)

The repo includes `environment.example` at the root for reference.

---

## Running locally (backend)

From repo root:

```bash
cd backend
. .venv/bin/activate
uvicorn app.main:app --reload
```

Type checking / tests:

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy --config-file mypy.ini app
```

---

## Frontend contract safety

The backend includes a **frontend API contract test** that asserts all API routes called by the frontend exist:

- Extractor: `backend/scripts/extract_frontend_contract.py`
- Test: `backend/tests/test_frontend_api_contract.py`

If you add/remove routes, run pytest; this test catches missing endpoints early.

---

## Git hooks (pre-commit / pre-push)

Hooks are configured via `.pre-commit-config.yaml` at repo root:

- **pre-commit stage**: ruff (only `F` and `E9`) scoped to `backend/`
- **pre-push stage**: backend mypy + backend pytest + cfn-lint + frontend lint/test/build

To run manually:

```bash
pre-commit run --hook-stage pre-commit --all-files
pre-commit run --hook-stage pre-push --all-files
```

---

## How to extend (the playbook)

### 1) Add a new API endpoint

- Create/edit a router in `backend/app/routers/<area>.py`
- Keep logic thin; call a repo or pipeline function
- Register it in `backend/app/main.py` via `app.include_router(...)`
- Run `backend` tests (frontend contract test will fail if you broke a used route)

### 2) Add a new DynamoDB-backed “thing”

- Add a new repo module in `backend/app/repositories/<area>_<thing>_repo.py`
  - Define `*_key(...)` helpers (`pk`/`sk`)
  - Implement `get/create/update/list` functions
- Use it from routers/pipeline/workers
- Prefer explicit function APIs over “generic repo classes”

### 3) Add/modify pipeline stages or stage computation

- Update `backend/app/stage_machine.py::compute_stage(...)`
- Ensure any mutations that can affect stage call `workflow.sync_for_rfp(...)`
- Update task templates in `backend/app/pipeline/workflow_task_templates.py` if needed

### 4) Add a side effect (Slack notification, async processing)

- Enqueue an outbox event with `repositories/outbox_repo.py::enqueue_event(...)`
- Add a handler in `workers/outbox_worker.py::dispatch_event(...)`
- Keep handlers small and idempotent when possible

### 5) Add a new integration

- Put external-client code under `backend/app/infrastructure/integrations/<vendor>/...`
- Keep secrets/config lookup in `settings.py` and/or Secrets Manager helpers
- Expose status via `routers/integrations.py` if useful

---

## “Where should this code live?”

Rule of thumb:

- **HTTP/controller concerns** → `routers/`
- **Pure business logic / transformations / orchestration** → `pipeline/` or top-level `workflow.py`
- **Persistence** → `repositories/`
- **External systems & SDKs** → `infrastructure/`
- **Async dispatch / polling loops** → `workers/`




