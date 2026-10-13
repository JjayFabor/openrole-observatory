# OpenRole Observatory

OpenRole Observatory is a job-data reliability platform that collects job listings directly from employer applicant-tracking-system sources, preserves historical observations, detects listing changes, and exposes source-backed listing data through an API.

The project is designed primarily as a data-engineering and backend-engineering system.

Instead of acting as another generic job board, OpenRole focuses on:

- direct-source job ingestion;
- source freshness;
- historical job versions;
- change detection;
- data lineage;
- data quality;
- replayable raw data;
- normalized canonical job records.

The initial supported ATS provider is **Greenhouse**.

Future providers may include:

- Lever
- Ashby
- Workable
- selected custom career pages

---

## Current Status

Deployment preparation targets **Render for FastAPI and cron** and **Vercel for
Next.js**, backed by production PostgreSQL and private R2. Task 1 validates
production configuration; Task 2 adds deployment templates and a single-operator
access boundary: dashboard Basic authentication and separate administrative API
bearer credentials. Public job reads remain public. See the
[Render/Vercel deployment guide](docs/deployment-render-vercel.md),
[production configuration](docs/production-configuration.md) and
[ADR 0004](docs/adrs/0004-render-vercel-administrative-access.md).
Actual provisioning, DB/R2 verification, backup/restore and the hosted release
gate remain pending; this is not a completed public deployment.

Neon CLI setup now links this directory to the selected `production` branch of
project `sweet-boat-68377250` in Singapore. The empty `neon.ts` policy was applied
successfully without changes or replacing the local database environment. See
[Neon setup](docs/neon-setup.md). Application tables, production connection
settings and R2 still require the deployment infrastructure task.

After Phase 4, the requested Greenhouse automation increment adds automatic
board discovery and an external six-hour synchronization timer. The catalogue
provides candidates; Greenhouse metadata verifies each new company before
registration, and the existing ingestion pipeline supplies all listing facts.
Normal cycles admit up to 25 new boards and sync all active Greenhouse sources.
See [source automation](docs/source-automation.md) for installation, coverage,
logs and deployment, and the updated [Word deployment guide](docs/OpenRole-Deployment-Guide.docx).

On a Linux host with a running user systemd manager, from `backend`:

```bash
uv run python -m app.cli.install_automation_timer --start-now
systemctl --user status openrole-greenhouse-automation.timer
```

The timer runs at 00:00, 06:00, 12:00 and 18:00 Asia/Manila while the host is on.
The API, frontend, PostgreSQL and raw storage still need the usual local setup.
The completed phase descriptions below record their original delivery scope.

OpenRole has completed:

> **Phase 1 - Greenhouse Ingestion Foundation**

> **Phase 2 - Change and Lifecycle Intelligence**

Phase 2 Tasks 24–33 add field-change history and conservative lifecycle
reconciliation to normal synchronization. Safe runs reset tentative absences,
record reappearance, confirm prior absences, and detect new first absences before
the PipelineRun completes. CLI and sync responses include a lifecycle summary.
Read-only administrative APIs expose current jobs, version/change/lifecycle
history, and source health. Lifecycle changes and successful run finalization
commit together, so a later failure rolls back lifecycle decisions. Clean
migrations, end-to-end histories, failure injection, and API inspection passed.
See [the Phase 2 completion report](docs/phase-2-completion.md) for evidence and
current limitations. Developer understanding review remains pending.

Phase 3 is **OpenRole Internal Dashboard**. Its Next.js frontend reads operational
facts through FastAPI: system readiness, source health, jobs and persisted
content/lifecycle history, pipeline runs, and quarantine diagnostics. Source
Detail provides the sole write action, guarded manual synchronization. Task 42
completes the previously deferred Job Detail and Runs prerequisites and audits
navigation, security, responsive behavior, and regressions. See the
[Phase 3 completion report](docs/phase-3-completion.md) for the actual verification
verdict and limitations; developer understanding review remains pending.
Greenhouse remains the only implemented provider. Source administration, polling,
authentication, and additional providers remain deferred. See
[the frontend setup guide](frontend/README.md) and [Phase 3 scope](docs/phase-3.md).

Phase 4 Task 43 adds a separate read-only public jobs API at
`/api/v1/public/jobs` and `/api/v1/public/jobs/{job_id}`. Discovery includes
observed listings from active sources; known historical listings remain
addressable by ID. See the [public API contract](docs/phase-4.md#task-43-delivered-public-api-contract).
Task 44 adds the public landing page at `/` and its separate header/main/footer
shell. Task 45 replaces `/jobs` with public API-backed search, location/type
filters, freshness-first results and URL-driven pagination. Selected listings
open current public detail with safe descriptions, factual lifecycle/observation
evidence and an original-source action (Task 46). Task 47 adds bounded recent
material changes through a separate public-safe endpoint. Task 48 adds factual
metadata, canonical/indexing policy, robots and a runtime sitemap; JobPosting
markup is deferred until required employer facts are available. Task 49 closes
Phase 4 with passing integration/security/accessibility verification; see
[the Phase 4 completion report](docs/phase-4-completion.md) for evidence and limits.
Developer understanding review remains pending, and public deployment still
requires hosted infrastructure/access verification and a configured site origin
for indexing. The deployment increment implements the administrative guards.
The static landing works without FastAPI; discovery/detail need it. See
[frontend setup and routes](frontend/README.md#public-shell-and-landing--task-44).

Phase 1 focuses on building a reliable ingestion pipeline before adding frontend features, search, AI enrichment, or additional ATS providers.

The initial pipeline is:

```text
Greenhouse API
      ↓
Fetch jobs
      ↓
Store raw response in Cloudflare R2
      ↓
Validate
      ↓
Normalize
      ↓
Persist to PostgreSQL
      ↓
Detect new / changed / unchanged jobs
      ↓
Preserve job history
      ↓
Expose pipeline information through FastAPI
```

---

## Goals

The project aims to answer questions such as:

- Is this job still published by the employer?
- When was it last observed?
- When was it first observed?
- Has its title changed?
- Has its location changed?
- Has its workplace arrangement changed?
- Has its compensation changed?
- What source produced the information?
- Can the normalized record be traced back to the original ATS response?

Future versions may also provide:

- duplicate-job detection;
- international-hiring evidence;
- visa and relocation evidence;
- skill-demand analytics;
- employer hiring activity;
- listing-lifespan analytics;
- saved searches;
- alerts;
- external webhooks;
- public job-search pages.

---

## Architecture

OpenRole begins as a modular Python application.

```text
                Public ATS
                Greenhouse
                    │
                    ▼
             Source Connector
                    │
                    ▼
            Raw Source Response
                    │
                    ▼
              Cloudflare R2
               Bronze Layer
                    │
                    ▼
                Validation
                    │
             ┌──────┴──────┐
             ▼             ▼
          Valid        Quarantine
             │
             ▼
        Normalization
             │
             ▼
          PostgreSQL
          Silver Layer
             │
             ▼
       Change Detection
             │
       ┌─────┴──────┐
       ▼            ▼
 Current State   History
       │            │
       └─────┬──────┘
             ▼
          FastAPI
```

The initial architecture intentionally avoids unnecessary distributed infrastructure.

Phase 1 does **not** require:

- Kafka
- Spark
- Redis
- Celery
- Elasticsearch
- Airflow
- Prefect
- dbt
- Kubernetes

These may be evaluated later only when a concrete requirement justifies them.

---

## Data Layers

OpenRole follows a simple Bronze / Silver / future Gold model.

### Bronze

Raw source data.

Stored in:

```text
Cloudflare R2
```

Properties:

- immutable;
- source-specific;
- timestamped;
- replayable.

Example:

```text
bronze/
  greenhouse/
    {source_connection_id}/
      year=2026/
        month=09/
          day=28/
            run={pipeline_run_id}/
              jobs.json
```

---

### Silver

Normalized operational data.

Stored in PostgreSQL.

Examples:

- companies;
- ATS source connections;
- jobs;
- job versions;
- source observations;
- pipeline runs;
- quarantine records.

---

### Gold

Future analytical datasets.

Potential examples:

- currently verified jobs;
- company hiring activity;
- job listing lifespan;
- skill-demand trends;
- workplace-model trends;
- international-hiring evidence.

Gold-layer implementation is outside Phase 1.

---

## Core Data Concepts

OpenRole separates job identity from job state.

```text
Job
↓
Stable identity

JobVersion
↓
Observed state at a point in time
```

Example:

```text
Job #123

Version 1
Location: Remote

Version 2
Location: Berlin — Hybrid
```

Historical versions are preserved rather than overwritten.

A job version should be traceable through:

```text
JobVersion
    ↓
SourceObservation
    ↓
PipelineRun
    ↓
RawSnapshot
    ↓
Cloudflare R2
```

---

## Phase 1 Scope

Phase 1 includes:

- FastAPI application foundation;
- PostgreSQL;
- SQLAlchemy;
- Alembic migrations;
- Greenhouse connector;
- company/source configuration;
- Cloudflare R2 raw storage;
- local filesystem storage;
- source validation;
- canonical normalization;
- source observations;
- stable job identity;
- job versioning;
- deterministic content hashing;
- idempotent ingestion;
- quarantine handling;
- pipeline metrics;
- structured logging;
- CLI ingestion;
- minimal administrative API;
- automated tests.

---

## Phase 1 Non-Goals

The following are deliberately excluded:

- frontend dashboard;
- user authentication;
- subscriptions;
- payments;
- email notifications;
- webhooks;
- AI enrichment;
- visa-sponsorship extraction;
- skill extraction;
- semantic deduplication;
- job recommendations;
- resume generation;
- automatic applications;
- LinkedIn scraping;
- Indeed scraping;
- Lever;
- Ashby;
- Workable;
- analytics marts;
- dbt;
- Prefect;
- Kafka;
- Spark.

See:

```text
docs/phase-1.md
```

for the full implementation contract.

---

## Technology Stack

### Backend

- Python
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic

### Database

- PostgreSQL
- Neon planned for hosted production database

### Frontend

- Next.js App Router and TypeScript
- Tailwind CSS and a small shadcn/ui component base
- pnpm

### Raw Storage

- Cloudflare R2
- local filesystem implementation for development/tests

### HTTP

- `httpx`

The Greenhouse adapter uses an injected asynchronous client to request:

```text
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
```

It returns the exact response bytes and transport metadata. Validation,
object-storage writes, and database persistence remain separate steps.

### Testing

- pytest

### Code Quality

- Ruff
- static type checking where practical

### Local Development

- Docker Compose
- PostgreSQL

---

## Repository Structure

Expected structure:

```text
openrole/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── companies/
│   │   ├── database/
│   │   ├── ingestion/
│   │   ├── jobs/
│   │   ├── pipeline_runs/
│   │   ├── quarantine/
│   │   ├── shared/
│   │   ├── sources/
│   │   │   └── greenhouse/
│   │   ├── storage/
│   │   └── cli/
│   │
│   ├── migrations/
│   ├── tests/
│   └── pyproject.toml
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/api/
│   └── package.json
│
├── docs/
│   ├── product-spec.md
│   ├── architecture.md
│   ├── data-model.md
│   └── phase-1.md
│
├── fixtures/
│   └── greenhouse/
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Documentation

The project documentation is intentionally separated by responsibility.

### Product specification

```text
docs/product-spec.md
```

Defines:

- product problem;
- users;
- goals;
- product principles;
- MVP scope;
- non-goals.

---

### Architecture

```text
docs/architecture.md
```

Defines:

- system components;
- data flow;
- storage responsibilities;
- ingestion architecture;
- failure handling;
- observability;
- deployment direction.

---

### Data model

```text
docs/data-model.md
```

Defines:

- PostgreSQL entities;
- relationships;
- versioning;
- indexes;
- data lineage;
- ERDs;
- data-model invariants.

---

### Phase 1 specification

```text
docs/phase-1.md
```

Defines:

- exact implementation scope;
- acceptance criteria;
- test requirements;
- definition of done.

### Phase 1 completion report

```text
docs/phase-1-completion.md
```

Records the final migration, automated-test, live-smoke, schema, lineage,
security, and limitation audit used to close Phase 1.

### Phase 2 specification and completion report

`docs/phase-2.md` defines field-change, presence-safety, lifecycle, and read-API
contracts. [docs/phase-2-completion.md](docs/phase-2-completion.md) records the
clean-database verification, acceptance scenarios, atomicity hardening, API
checks, limitations, and Phase 3 readiness review.

---

## Local Development

### Requirements

Install:

- Python
- Docker
- Docker Compose
- Git
- Node.js 22 LTS and pnpm (for the dashboard)

Cloudflare R2 is not required for normal local development.

Local development can use filesystem-backed object storage.

---

## Environment Configuration

Copy:

```bash
cp .env.example .env
```

Expected variables include:

```text
APP_ENV=development
LOG_LEVEL=INFO

DATABASE_URL=

OBJECT_STORAGE_BACKEND=filesystem
LOCAL_STORAGE_PATH=.local-data

R2_ENDPOINT_URL=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_REGION=auto

HTTP_CONNECT_TIMEOUT_SECONDS=5
HTTP_READ_TIMEOUT_SECONDS=30
```

Do not commit real credentials.

### Cloudflare R2 storage

Local development continues to use filesystem storage by default. To select R2,
set `OBJECT_STORAGE_BACKEND=r2` and provide the endpoint, access key, secret key,
and private bucket name shown above. R2 credentials should come from an ignored
local `.env` file and should be scoped to object operations on one development or
test bucket rather than account-wide administration.

R2 uses its S3-compatible endpoint with region `auto`. OpenRole creates raw
objects conditionally, so an existing key is never silently overwritten.

The normal test suite does not contact R2. To verify the adapter against a
dedicated private development/test bucket, configure the R2 variables in your
environment and run:

```bash
RUN_R2_INTEGRATION_TESTS=true \
uv run pytest tests/integration/test_r2_storage.py
```

The test uses a unique `integration-tests/` key and deletes only that generated
test object through the SDK during cleanup. Never point it at production Bronze
objects.

---

## Start PostgreSQL

```bash
docker compose up -d postgres
```

PostgreSQL listens on host port `5434` by default and on port `5432` inside the
container. Set `POSTGRES_PORT` to use a different host port.

Verify the container is healthy before starting the application.

---

## Install Backend Dependencies

From:

```text
backend/
```

install the locked Python dependencies with `uv`:

```bash
uv sync
```

`uv` creates a virtual environment in `backend/.venv`. Use `uv run` for project
commands so they execute with that environment and the locked dependencies.

---

## Database Migrations

From `backend/`, inspect the current migration state:

```bash
uv run alembic current
uv run alembic heads
uv run alembic history
```

Apply all pending migrations:

```bash
uv run alembic upgrade head
```

Roll back one revision with:

```bash
uv run alembic downgrade -1
```

The Phase 1 migration chain creates companies and source connections, pipeline
runs and raw snapshots, jobs and job versions, source-observation lineage, and
quarantine records. When a later task changes the schema, create a candidate
revision with:

```bash
uv run alembic revision --autogenerate -m "describe schema change"
```

Never apply an autogenerated migration without reviewing it. Inspect both
`upgrade()` and `downgrade()` for column types, nullability, defaults, indexes,
constraints, foreign keys, and accidental destructive operations.

Inspect the local PostgreSQL schema from the repository root with:

```bash
docker compose exec postgres psql -U openrole -d openrole
```

Inside `psql`, use `\dt` to list tables and, later, `\d companies` to inspect a
specific table. Do not modify schemas manually outside Alembic migrations.

---

## Seed Development Data

Create or reuse a development company and Greenhouse source connection by
passing the public Greenhouse board token:

```bash
uv run python -m app.cli.seed_dev <greenhouse-board-token>
```

Optional labels can be supplied with `--company-name` and `--company-slug`.
Running the command again with the same board token is safe: it reports the
existing source instead of creating a duplicate. The seed creates:

- a sample company;
- a Greenhouse source connection.

Jobs should normally enter the system through the ingestion pipeline rather than being manually seeded.

---

## Run the Greenhouse Pipeline

From `backend/`, synchronize one configured, active Greenhouse source:

```bash
uv run python -m app.cli.sync_source <source_connection_id>
```

A successful first run should produce output similar to:

```text
Pipeline completed

Provider: Greenhouse

Fetched:       8
Valid:         8
Quarantined:   0

New:           8
Changed:       0
Unchanged:     0
```

Running the same source again without changes should produce:

```text
Fetched:       8

New:           0
Changed:       0
Unchanged:     8
```

This behavior verifies basic idempotency.

The command exits with status `0` for both `completed` and
`completed_with_errors`, because the source synchronization completed in both
cases and quarantined records remain visible for review. Source, storage, or
pipeline failures exit with status `1` and print a stable error code without raw
response content or credentials.

---

## Run the API

From `backend/`:

```bash
uv run uvicorn app.main:app --reload
```

Verify process health and PostgreSQL readiness separately:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`/health` reports whether the API process is alive. `/ready` executes a
non-mutating `SELECT 1` query and returns HTTP 503 when PostgreSQL is unavailable.

The internal API includes pipeline operations, history inspection, and the
Phase 3 Jobs explorer read:

```text
GET  /health
GET  /ready

GET  /api/v1/pipeline-runs
GET  /api/v1/pipeline-runs/{run_id}

POST /api/v1/sources/{source_id}/sync

GET  /api/v1/jobs
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs/{job_id}/versions
GET  /api/v1/jobs/{job_id}/changes
GET  /api/v1/jobs/{job_id}/lifecycle
GET  /api/v1/sources/{source_id}
```

Trigger a synchronous administrative sync:

```bash
curl -X POST \
  http://localhost:8000/api/v1/sources/<source-id>/sync
```

The request waits until the run reaches `completed` or
`completed_with_errors`. Phase 1 deliberately does not use FastAPI background
tasks or a job queue.

Inspect recent runs and one run's metrics:

```bash
curl 'http://localhost:8000/api/v1/pipeline-runs?limit=50&offset=0'
curl http://localhost:8000/api/v1/pipeline-runs/<run-id>
```

The pipeline-run list is ordered by most recent `started_at` first.

List current jobs with backend pagination and optional lifecycle/source/search
filters. The response includes `items`, filtered `total`, `limit`, and `offset`:

```bash
curl 'http://localhost:8000/api/v1/jobs?limit=25&offset=0&lifecycle_status=observed&q=engineer'
```

`source_connection_id` accepts an optional UUID. Search is trimmed, limited to
200 characters, and matches literal case-insensitive text in current title,
location text, or external job ID. Ordering is last seen descending, then job ID
ascending. Safe company/source summaries and only current-version display fields
are returned; a missing current version is an invariant error. See the
[Task 36 contract](docs/phase-3.md#task-36-jobs-explorer).

Inspect a known job and its source without triggering ingestion:

```bash
curl http://localhost:8000/api/v1/jobs/<job-id>
curl 'http://localhost:8000/api/v1/jobs/<job-id>/versions?limit=50&offset=0'
curl 'http://localhost:8000/api/v1/jobs/<job-id>/changes?limit=50&offset=0'
curl 'http://localhost:8000/api/v1/jobs/<job-id>/lifecycle?limit=50&offset=0'
curl http://localhost:8000/api/v1/sources/<source-id>
```

Job detail combines stable identity/current lifecycle state with exactly one
current canonical version, including for `not_observed` jobs. A missing current
version returns HTTP 500 with `CURRENT_JOB_VERSION_MISSING`, rather than a null
version. Unknown jobs/sources return stable HTTP 404 error envelopes; existing
jobs with empty histories return empty collections.

The pipeline-run list accepts optional `status` and `source_connection_id` filters,
applied before `started_at DESC, id DESC` pagination. It retains `limit=50` by
default (maximum 100), a nonnegative offset bounded to the PostgreSQL integer
range, and its existing `items/limit/offset` response without a total.

History pagination defaults to `limit=50&offset=0`, with `1 <= limit <= 100` and
`offset >= 0`. Versions and changes use `items`; lifecycle history uses `events`
alongside its current state. Orders are:

- versions: `version_number ASC`;
- changes: destination version number, field name alphabetically, then event ID;
- lifecycle events: `occurred_at`, `created_at`, then event ID, all ascending.

Changes return persisted field values as JSON, including full description changes.
Versions include canonical metadata, source-observation IDs and content hashes for
administrative provenance. Salary Decimals serialize as exact strings; timestamps
retain their timezone. No history endpoint writes freshness, lifecycle state, or
events.

Lifecycle `no_longer_observed_at` is the observation time at which OpenRole
confirmed absence, rather than the exact employer removal time. An observed job
can retain that timestamp and `reappeared_at` after reappearance. Event history
records past transitions separately from the current state.

Source health returns attempted/successful sync timestamps and only its latest
run (`started_at DESC`, then ID descending), including safe error code/summary
when that run failed. A failed latest run retains the older successful-sync
timestamp; a never-synced source returns null timestamps and `latest_run`.
Source configuration and external account keys are excluded from this response.

> **Security warning:** These administrative endpoints do not have
> authentication. Do not expose them publicly. Keep them restricted to a local
> or private network, or protect them with platform-level access controls.

Phase 1 operations are documented in `docs/phase-1.md`; Phase 2 inspection is
documented in `docs/phase-2.md`.

### Public jobs API — Task 43

These separate unauthenticated routes are read-only:

```text
GET /api/v1/public/jobs
GET /api/v1/public/jobs/{job_id}
```

```bash
curl 'http://localhost:8000/api/v1/public/jobs?q=backend&location=manila&limit=25&offset=0'
curl 'http://localhost:8000/api/v1/public/jobs?workplace_type=remote&employment_type=full_time'
curl http://localhost:8000/api/v1/public/jobs/<job-id>
```

Search is literal case-insensitive containment in current title, company name,
or location text. Location searches canonical location text; workplace/employment
filters match exact supported values. Filters intersect. Pagination returns a
filtered total and orders by `last_seen_at DESC, job.id ASC`. Discovery requires
an observed job, an active source, and exactly one current canonical version;
detail remains available for not-observed jobs and inactive sources.

Public schemas expose listing content, company display fields, source provider,
exact salary strings and observation timestamps. Detail adds description,
validated HTTP(S) source URL and lifecycle timestamps. Internal IDs, hashes,
metadata and configuration remain excluded. Stored descriptions are untrusted
HTML and require sanitization before rendering. Production Greenhouse mapping
leaves unsupported structured fields null rather than inferring them.

Public routes do not remove access restrictions from administrative routes or
the dashboard. Publish only the intended read surface through deployment access
rules. CORS, authentication and application rate limiting are unchanged; public
load may later require a measured cache/rate-limit strategy. Full contract:
[Task 43](docs/phase-4.md#task-43-delivered-public-api-contract).

---

## Run the Internal Dashboard

Keep FastAPI running in one terminal. In another terminal, from the repository
root:

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

Open `http://localhost:3000/dashboard`. The Next.js server uses
`OPENROLE_API_BASE_URL` from `frontend/.env.local` to call FastAPI; the browser
does not receive this configuration or connect to PostgreSQL. Other dashboard
routes support operational exploration. If FastAPI is stopped, the shell still
renders and status checks display unavailable states. Reload to check again.

The overview also reads recent pipeline activity and, when
`OPENROLE_DEFAULT_SOURCE_ID` is configured, that source's synchronization health.
The recent list spans all sources; it is not filtered by the monitored source.
Without the optional ID, source monitoring shows an empty state. The setup guide
explains this temporary development limitation and UTC timestamp presentation.

See [frontend/README.md](frontend/README.md) for lint, type checking, tests,
production builds, and the server/client component boundary.

---

## Run Tests

From `backend/`:

```bash
uv run pytest
uv run ruff check .
uv run mypy
```

The Phase 1 test suite should cover:

- Greenhouse mapping;
- deterministic content hashing;
- idempotent ingestion;
- changed-job versioning;
- current-version uniqueness;
- source observations;
- quarantine behavior;
- database constraints;
- full fixture-based pipeline execution.

---

## Greenhouse Fixtures

Local tests should not depend on live Greenhouse requests.

Fixtures should include:

```text
fixtures/greenhouse/jobs_v1.json
fixtures/greenhouse/jobs_v2.json
fixtures/greenhouse/jobs_invalid_record.json
fixtures/greenhouse/jobs_invalid_top_level.json
fixtures/greenhouse/jobs_optional_fields.json
```

These fixtures model Greenhouse's provider-native response contract. They are
validated into Greenhouse source models before the Greenhouse mapper produces
provider-independent OpenRole canonical job inputs. The mapper preserves source
HTML descriptions, maps free-form locations to `location_text`, and retains only
selected departments and offices in canonical metadata. It does not guess
structured locations, workplace types, employment types, or salaries. One
malformed child record is isolated without making an otherwise usable top-level
response fail.

Recommended test sequence:

```text
jobs_v1
↓
initial jobs created

jobs_v1 again
↓
no duplicate jobs or versions

jobs_v2
↓
only changed jobs receive new versions

jobs_invalid_record
↓
malformed records quarantined
valid records still processed
```

---

## Data Lineage

One of OpenRole's core requirements is traceability.

For any normalized job version, the system can answer:

```text
Which source record produced this?
Which pipeline run observed it?
Which raw snapshot contains it?
Where is that raw snapshot stored?
```

Conceptually:

```text
job_version
    ↓
source_observation
    ↓
raw_snapshot
    ↓
pipeline_run
    ↓
source_connection
    ↓
company
    ↓
filesystem or R2 object
```

This lineage must not be broken by future transformations.

---

## Idempotency

OpenRole must support repeated ingestion safely.

The following combination identifies a stable source job:

```text
source_connection_id
+
external_job_id
```

Repeated ingestion of unchanged data should:

- create a new source observation;
- update `last_seen_at`;
- not create another job;
- not create another version.

Changed canonical content should create a new immutable job version.

---

## Failure Philosophy

OpenRole follows several important principles.

### Preserve before transforming

Raw source responses should be stored before canonical transformation.

### Fail visibly

Invalid records must be quarantined or reported rather than silently discarded.

### Do not confuse source failure with job removal

If an ATS request fails, existing jobs remain unchanged.

### Keep historical versions

Previous job states must not be overwritten when a listing changes.

### Prefer observed facts

OpenRole reports what it observed.

It should not claim that an employer is deceptive, that a job is fake, or that a listing is a ghost job based only on public listing data.

---

## Development Principles

### Correctness before scale

The initial project should prefer understandable and testable pipelines over distributed infrastructure.

### Source isolation

Greenhouse-specific behavior belongs inside the Greenhouse connector and mapper.

Core job logic should operate on canonical models.

### Replayability

Raw source data should allow transformations to be rerun after mapper bugs are fixed.

### Explicit contracts

Source schemas, canonical schemas, database constraints, and API responses should be typed and testable.

### Small phases

Do not begin the next phase until the current phase meets its documented definition of done.

---

## Roadmap

### Phase 1

Greenhouse ingestion foundation.

```text
Greenhouse
→ R2
→ validation
→ normalization
→ PostgreSQL
→ version history
→ FastAPI
```

### Phase 2

Historical change detection.

Potential additions:

- field-level diffs;
- listing disappearance;
- reappearance;
- lifecycle events.

### Phase 3

OpenRole Internal Dashboard.

Tasks 34–42 deliver operational overview, jobs/history, runs, quarantine, sources,
and manual sync. The completion report records verification and remaining limits.
Additional ATS providers remain deferred; Greenhouse is the implemented provider.

### Phase 4

Public Job Discovery Product. See [the Phase 4 contracts and delivery record](docs/phase-4.md).
Tasks 43–49 deliver and verify the public jobs read boundary, landing page, separate
public shell, discovery, current detail, recent material changes and SEO policy.
Engineering verification is PASS; see [the completion report](docs/phase-4-completion.md).
The internal dashboard remains separate. Data-quality improvements remain
possible later work.

### Phase 5

Entity resolution and duplicate detection.

### Phase 6

Job enrichment.

Potential:

- skills;
- workplace type;
- international hiring;
- relocation;
- visa-sponsorship evidence.

### Phase 7

Analytical data products.

Potential:

- dbt;
- Parquet;
- DuckDB;
- labor-market analytics.

### Phase 8

Expanded product and consumer API, beyond the proposed Phase 4 discovery release.

Potential:

- richer company profiles;
- saved searches;
- alerts;
- developer API.

---

## Learning Objectives

OpenRole is also intended as a practical data-engineering learning project.

The project should provide hands-on experience with:

- Python data pipelines;
- API ingestion;
- FastAPI;
- PostgreSQL;
- SQLAlchemy;
- object storage;
- Cloudflare R2;
- data normalization;
- immutable raw data;
- Bronze/Silver/Gold architecture;
- idempotency;
- incremental ingestion;
- data lineage;
- historical modeling;
- slowly changing data;
- schema evolution;
- data-quality handling;
- quarantine patterns;
- orchestration;
- analytical processing;
- webhooks;
- observability.

Later phases may introduce:

- dbt;
- DuckDB;
- Parquet;
- Prefect;
- data marts;
- entity resolution.

These should be introduced because the system needs them, not simply to increase the number of technologies used.

---

## Contributing

The project currently follows a phase-based implementation process.

Before making substantial changes:

1. read the relevant documentation;
2. confirm the feature belongs to the current phase;
3. understand its impact on lineage and historical data;
4. update tests;
5. update documentation if architectural behavior changes.

Do not add unrelated infrastructure or product features without documenting the reason.

---

## License

A project license has not yet been selected.

Add an explicit open-source or proprietary license before public distribution if required.
