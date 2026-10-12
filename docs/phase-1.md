# OpenRole Observatory — Phase 1 Implementation Specification

## 1. Purpose

Phase 1 establishes the ingestion foundation for OpenRole Observatory.

The goal is to reliably ingest public job listings from Greenhouse, preserve the original source response in Cloudflare R2, normalize supported records into PostgreSQL, maintain job identity and version history, and expose enough operational information to verify that the pipeline is working correctly.

Phase 1 is intentionally narrow.

It is not a user-facing product release.

It is the first production-quality data pipeline on which later phases will depend.

---

## 2. Phase 1 Objective

The system must support this complete flow:

```text
Configured Greenhouse company
        ↓
Acquire source execution lock
        ↓
Create pipeline run
        ↓
Fetch public job listings
        ↓
Store raw API response through ObjectStorage
        ↓
Validate response
        ↓
Normalize supported records
        ↓
Resolve stable job identity
        ↓
Persist current state and version history
        ↓
Quarantine invalid records
        ↓
Record pipeline metrics
        ↓
Expose run status through FastAPI
```

Phase 1 is complete only when this flow works repeatedly and predictably.

---

## 3. Primary Success Condition

Given the same Greenhouse source data multiple times:

```text
Run 1
→ create jobs

Run 2
→ do not create duplicates

Run 3 with one changed record
→ create one new job version

Run 4 with one invalid record
→ quarantine that record without corrupting valid records
```

The system must preserve lineage back to the raw object-storage snapshot for every created job version.

---

## 4. In Scope

Phase 1 includes:

- FastAPI application foundation;
- PostgreSQL database;
- SQLAlchemy models;
- Alembic migrations;
- Greenhouse source connector;
- source configuration;
- pipeline-run tracking;
- raw response persistence to Cloudflare R2;
- local development storage abstraction;
- source-response validation;
- canonical job mapping;
- source observation creation;
- stable job identity;
- job versioning;
- deterministic content hashing;
- idempotent re-ingestion;
- record-level quarantine;
- structured logging;
- pipeline metrics;
- CLI-triggered ingestion;
- minimal administrative API;
- automated tests;
- local fixtures;
- `.env.example`;
- basic developer documentation.

---

## 5. Explicitly Out of Scope

Do not implement any of the following in Phase 1:

- Next.js frontend;
- public job-search UI;
- authentication;
- users;
- saved searches;
- subscriptions;
- billing;
- email notifications;
- webhooks;
- n8n;
- Prefect;
- Dagster;
- Airflow;
- dbt;
- DuckDB;
- Parquet data products;
- Kafka;
- Redis;
- Celery;
- Spark;
- Elasticsearch;
- AI enrichment;
- visa-sponsorship extraction;
- skill extraction;
- job recommendations;
- resume matching;
- semantic deduplication;
- Lever connector;
- Ashby connector;
- Workable connector;
- LinkedIn scraping;
- Indeed scraping;
- job-application automation;
- recruiter workflows;
- analytics marts;
- ranking or recommendation algorithms.

If an implementation decision would require one of these, document the reason and defer it rather than expanding the phase automatically.

---

## 6. Repository State

The Phase 1 implementation uses these primary boundaries:

```text
openrole_observatory/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── cli/
│   │   ├── companies/
│   │   ├── database/
│   │   ├── ingestion/
│   │   ├── jobs/
│   │   ├── pipeline_runs/
│   │   ├── quarantine/
│   │   ├── raw_snapshots/
│   │   ├── source_observations/
│   │   ├── sources/greenhouse/
│   │   ├── storage/
│   │   ├── composition.py
│   │   ├── config.py
│   │   └── main.py
│   ├── migrations/
│   ├── tests/
│   │   ├── integration/
│   │   └── fixtures/greenhouse/
│   └── pyproject.toml
├── docs/
│   ├── product-spec.md
│   ├── architecture.md
│   ├── data-model.md
│   ├── phase-1.md
│   └── phase-1-completion.md
├── docker-compose.yml
├── .env.example
└── README.md
```

The domains remain separate while sharing one deployable modular monolith.

---

## 7. Phase 1 Data Model

Implement these tables:

```text
companies
source_connections
pipeline_runs
raw_snapshots
source_observations
jobs
job_versions
quarantine_records
```

The schema must follow `docs/data-model.md`.

Important constraints include:

```text
UNIQUE(source_connections.provider, source_connections.external_account_key)

UNIQUE(jobs.source_connection_id, jobs.external_job_id)

UNIQUE(job_versions.job_id, job_versions.version_number)
```

A partial unique index should enforce at most one current version per job:

```sql
CREATE UNIQUE INDEX uq_job_versions_current
ON job_versions(job_id)
WHERE is_current = TRUE;
```

---

## 8. Greenhouse Connector

The Greenhouse connector is the only ATS connector required in Phase 1.

It should accept a configured public board identifier and retrieve the currently published jobs for that board.

Conceptual interface:

```python
class GreenhouseConnector:
    async def fetch_jobs(
        self,
        source: SourceConnection,
    ) -> GreenhouseFetchResult:
        ...
```

The connector should return:

```text
raw response body
HTTP metadata
retrieval timestamp
parsed top-level response
```

It must not persist data directly.

---

## 9. Connector Responsibilities

The connector is responsible for:

- URL construction;
- request execution;
- timeout handling;
- HTTP status handling;
- source-level response validation;
- provider-specific error mapping;
- returning the unmodified response body;
- returning parsed Greenhouse job records.

It is not responsible for:

- R2 persistence;
- PostgreSQL persistence;
- canonical job creation;
- job versioning;
- quarantine persistence;
- change detection;
- business-level retry scheduling.

---

## 10. Greenhouse Source Validation

Define provider-specific Pydantic schemas for the portions of the Greenhouse response needed in Phase 1.

Validation should detect:

- missing external job IDs;
- missing title where title is required;
- unexpected top-level shape;
- invalid URL structure where required;
- invalid timestamp shape where used;
- malformed nested location data.

Do not reject the entire source response because one individual job record is invalid unless the top-level response itself cannot be parsed safely.

---

## 11. Raw Storage Requirements

On every successful source fetch, preserve the raw response before canonical transformation.

Target sequence:

```text
HTTP response received successfully
        ↓
Write raw bytes to object storage
        ↓
Create raw_snapshot metadata
        ↓
Proceed with record normalization
```

If R2/raw storage fails, do not continue silently into normalization in production mode.

The pipeline should fail because source replayability would be lost.

---

## 12. Storage Abstraction

Implement:

```python
class ObjectStorage(Protocol):
    async def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredObject:
        ...

    async def get_bytes(
        self,
        key: str,
    ) -> bytes:
        ...

    async def exists(
        self,
        key: str,
    ) -> bool:
        ...
```

Initial implementations:

```text
FilesystemObjectStorage
R2ObjectStorage
```

Use filesystem storage for most local development and automated tests.

Use R2 in production. The later approved single-host beta deployment also permits
explicitly configured persistent filesystem storage. Production Settings requires
an explicit backend and an absolute filesystem path; there is no implicit
development-storage fallback. See [production configuration](production-configuration.md).

---

## 13. R2 Key Format

Raw objects should use a deterministic partition-like path:

```text
bronze/
  greenhouse/
    {source_connection_id}/
      year={YYYY}/
        month={MM}/
          day={DD}/
            run={pipeline_run_id}/
              jobs.json
```

Example:

```text
bronze/greenhouse/019abc.../
year=2026/
month=09/
day=28/
run=019def.../
jobs.json
```

Do not place arbitrary company names directly into storage paths unless they are safely normalized.

Internal IDs are preferred.

The date partition comes from the Greenhouse fetch result's `retrieved_at`
timestamp after conversion to UTC. The acquisition stage stores the exact
response bytes, uses `application/json` when the response has no content type,
and copies the returned `StoredObject` key, hash, content type, and byte length
into `raw_snapshots`. It does not parse the response, so `record_count` remains
null.

Precondition reads and snapshot insertion use short database transactions. The
Greenhouse request and object upload occur between them without holding a
database transaction open. If the fetch fails, no storage write occurs; if the
storage write fails, no snapshot row is created. If storage succeeds but the
database insert fails, the failure is surfaced and the immutable object key is
logged as a possible orphan. The storage interface intentionally has no general
delete operation, so raw acquisition does not attempt compensating cleanup. Retrying the
same run may encounter an existing object at its deterministic key.

The source-record processing stage reopens that stored object through
`ObjectStorage`, verifies the whole-response hash and byte length, then reuses
Greenhouse top-level and record-level validation. Invalid JSON or an unusable
top-level envelope fails the stage without changing `record_count`. Once the
`jobs` array is valid, `record_count` becomes its total length, including invalid
child records.

Valid records create `SourceObservation` rows with `jobs[index]` locators, the
snapshot retrieval time as `observed_at`, and a provider-native SHA-256 derived
from deterministic JSON serialization of the decoded record. Invalid child
records and later duplicate external IDs are returned as typed results and do
not create observations or quarantine rows yet. All observations and
`record_count` are committed atomically after validation. A snapshot with a
non-null count or any existing observation is rejected as already processed.

---

## 14. Canonical Mapping

The Greenhouse mapper converts validated provider records into canonical job input.

Conceptual output:

```python
CanonicalJobInput(
    external_job_id="123456",
    title="Backend Engineer",
    description="...",
    location_text="Berlin",
    city=None,
    region=None,
    country_code=None,
    workplace_type=None,
    employment_type=None,
    salary_min=None,
    salary_max=None,
    salary_currency=None,
    salary_period=None,
    source_url="https://...",
    source_published_at=None,
    source_updated_at=None,
    canonical_metadata={},
)
```

Unknown values must remain null.

The mapper must not infer fields without explicit rules.

---

## 15. Content Hashing

Create a deterministic hash from canonical source-derived content.

Use:

```text
SHA-256
```

The hash input should exclude operational metadata such as:

- ingestion time;
- database IDs;
- last seen time;
- pipeline-run ID.

It should include fields that represent listing content.

At minimum:

```text
title
description
location_text
city
region
country_code
workplace_type
employment_type
salary_min
salary_max
salary_currency
salary_period
source_url
source_published_at
source_updated_at
```

Canonical serialization must use stable ordering.

Hash behavior must be unit-tested.

---

## 16. Pipeline Run Lifecycle

Every ingestion creates a pipeline run.

State transitions:

```text
pending
    ↓
running
    ↓
completed
```

or:

```text
running
    ↓
completed_with_errors
```

or:

```text
running
    ↓
failed
```

`completed_with_errors` means:

> The source was processed, but one or more individual records were quarantined.

`failed` means:

> The source run could not complete reliably.

---

## 17. Pipeline Execution Flow

Phase 2 Task 31 extends this Phase 1 flow: SourceSyncService calls the new
non-finalizing `SnapshotIngestionOrchestrator.process_records()` path, reconciles
lifecycle under the existing source lock, and only then finalizes the run.
The standalone `process_snapshot()` path still supports the original Phase 1
processing/finalization contract. See `phase-2.md` for lifecycle ordering and skips.

Pseudo-flow:

```text
Acquire source lock
        ↓
Create pipeline run as pending
        ↓
Mark run as running
        ↓
Fetch Greenhouse response
        ↓
Persist raw response
        ↓
Create raw snapshot metadata
        ↓
Parse source records
        ↓
For each record:
    create observation
    validate
    normalize
    hash canonical state
    resolve job
    persist new/change/unchanged
    quarantine record-level failures
        ↓
Calculate run metrics
        ↓
Update source last-successful-sync
        ↓
Mark run completed/completed_with_errors
        ↓
Release source lock
```

---

## 18. Per-Record Persistence

For each valid record:

```text
BEGIN TRANSACTION

Create source observation

Find existing job by:
source_connection_id
+
external_job_id

IF no job:
    create job
    create version 1
    jobs_new += 1

ELSE:
    compare canonical content hash
    with current job version

    IF same:
        update job.last_seen_at
        jobs_unchanged += 1

    IF different:
        close current version
        create next version
        update job.last_seen_at
        jobs_changed += 1

COMMIT
```

Any persistence failure must roll back that record's transaction.

---

## 19. New Job Behavior

When a source job does not yet exist:

Create:

```text
jobs
job_versions version 1
source_observation
```

Set:

```text
first_seen_at = observation time
last_seen_at = observation time
lifecycle_status = observed
```

Version:

```text
version_number = 1
effective_from = observation time
effective_to = null
is_current = true
```

---

## 20. Unchanged Job Behavior

If the source job exists and the canonical content hash equals the current version hash:

Do:

```text
create source observation
update jobs.last_seen_at
increment jobs_unchanged
```

Do not:

```text
create new jobs row
create new job_version
```

---

## 21. Changed Job Behavior

If the source job exists and the canonical content hash differs:

Close current version:

```text
is_current = false
effective_to = observation time
```

Create:

```text
new job_version
version_number = previous + 1
effective_from = observation time
effective_to = null
is_current = true
```

Update:

```text
jobs.last_seen_at
```

Increment:

```text
jobs_changed
```

---

## 22. Quarantine Behavior

If one source record cannot be safely normalized:

- preserve the raw source response;
- create a quarantine record;
- record the raw-record locator;
- capture a stable error category;
- continue processing the remaining records if possible.

Example:

```text
error_category:
schema_validation_failed

error_message:
location field has unsupported structure
```

The entire pipeline should not fail because one record is malformed.

---

## 23. Pipeline-Level Failure Conditions

The entire run should fail if:

- source configuration is invalid;
- Greenhouse cannot be reached after configured retry behavior;
- the source returns an unusable top-level response;
- raw response cannot be preserved;
- database becomes unavailable;
- source lock cannot be safely maintained;
- an unexpected application failure makes run state unreliable.

A failed run must never mark existing jobs as removed or inactive.

---

## 24. Source Locking

Only one ingestion run per source connection should execute at a time.

Preferred Phase 1 approach:

```text
PostgreSQL advisory lock
```

or an equivalently simple database-backed mechanism.

The Phase 1 implementation uses a session-level PostgreSQL advisory lock held
on one dedicated database connection for the execution scope. This allows the
pipeline to use separate short transactions without holding a transaction open
during network or object-storage work. The lock must be acquired before a
pipeline-run record is created, and it must be released in cleanup whether the
execution succeeds or raises an exception.

If a source is already syncing:

```text
new run should not start concurrently or create another pipeline-run record
```

The API/CLI should return a clear result.

Do not introduce Redis for this requirement.

---

## 25. Retry Behavior

Keep retry behavior conservative.

HTTP source failures may retry:

```text
maximum attempts: 3
```

with bounded exponential backoff.

Example:

```text
1 second
3 seconds
9 seconds
```

Exact values should remain configurable.

Do not retry:

- validation errors;
- deterministic normalization errors;
- missing required source identifiers.

Those should be quarantined or fail immediately as appropriate.

---

## 26. Timeouts

All outbound HTTP requests must define explicit:

- connection timeout;
- read timeout;
- total timeout if supported.

Never rely on an infinite/default network wait.

Example configuration:

```text
HTTP_CONNECT_TIMEOUT_SECONDS
HTTP_READ_TIMEOUT_SECONDS
```

---

## 27. CLI Requirement

Phase 1 must support manual execution through a CLI command.

Usage:

```bash
uv run python -m app.cli.sync_source <source_connection_id>
```

The preferred implementation should use the same application service as the API.

Do not maintain separate pipeline logic for CLI and HTTP.

---

## 28. Minimal FastAPI Endpoints

Phase 1 only requires administrative/inspection endpoints.

### Health

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

Optional:

```http
GET /ready
```

to verify database connectivity.

---

### List pipeline runs

```http
GET /api/v1/pipeline-runs
```

Support basic pagination.

---

### Get pipeline run

```http
GET /api/v1/pipeline-runs/{run_id}
```

Return metrics and failure information.

---

### Trigger source sync

```http
POST /api/v1/sources/{source_id}/sync
```

For Phase 1, authentication may be omitted if the service is not publicly exposed.

Before production public exposure, authentication is mandatory.

---

## 29. Optional Inspection Endpoints

If useful for development:

```http
GET /api/v1/jobs
GET /api/v1/jobs/{job_id}
GET /api/v1/jobs/{job_id}/versions
```

These are allowed in Phase 1 but should remain simple.

Do not build complex search or filtering yet.

---

## 30. API Error Format

Use a consistent error structure.

Example:

```json
{
  "error": {
    "code": "SOURCE_SYNC_ALREADY_RUNNING",
    "message": "A sync is already active for this source.",
    "request_id": "req_123"
  }
}
```

Avoid returning raw Python exception messages.

---

## 31. Structured Logging

Every pipeline run should include:

```text
pipeline_run_id
source_connection_id
provider
company_id
```

where applicable.

Example:

```json
{
  "event": "pipeline_completed",
  "pipeline_run_id": "...",
  "source_connection_id": "...",
  "records_fetched": 50,
  "jobs_new": 49,
  "jobs_changed": 0,
  "jobs_unchanged": 0,
  "records_quarantined": 1,
  "duration_ms": 2812
}
```

---

## 32. Local Development Requirements

Local development should work without Cloudflare R2.

Minimum local dependencies:

```text
Python
PostgreSQL
Docker
```

Use:

```text
FilesystemObjectStorage
```

for raw data during most local development.

Example:

```text
.local-data/
  bronze/
```

The storage interface must make switching to R2 configuration-only.

---

## 33. Docker Compose

Provide local PostgreSQL through Docker Compose.

Minimum services:

```yaml
services:
  postgres:
```

Do not add:

- Redis;
- MinIO;
- Elasticsearch;
- Kafka;

unless required by an explicit later phase.

MinIO may be added optionally for S3 compatibility testing but should not become mandatory for normal development.

---

## 34. Fixtures

Create at least three Greenhouse fixtures.

### `jobs_v1.json`

Represents valid initial source state.

Example:

```text
3–10 valid jobs
```

---

### `jobs_v2.json`

Same source IDs as V1, except:

- one job changes location;
- one job changes title or description;
- remaining jobs stay unchanged.

This fixture tests versioning.

---

### `jobs_invalid_record.json`

Contains:

- valid records;
- at least one malformed record.

This fixture tests quarantine behavior.

---

## 35. Required Unit Tests

At minimum:

### Greenhouse mapping

```text
valid Greenhouse record
→ expected CanonicalJobInput
```

### Null preservation

```text
missing source field
→ canonical field remains null
```

### Content hash determinism

```text
same canonical content
→ same hash
```

### Hash sensitivity

```text
meaningful field changes
→ different hash
```

### Hash ignores operational metadata

```text
different observed_at
→ same content hash
```

### Error mapping

```text
unsupported source record
→ expected validation/normalization error
```

---

## 36. Required Integration Tests

Use PostgreSQL.

### New job ingestion

Assert:

```text
job created
version 1 created
observation created
```

### Repeated identical ingestion

Assert:

```text
same jobs row
no new job version
new observation exists
last_seen_at updated
```

### Changed job ingestion

Assert:

```text
same job
old version closed
new version created
one current version
```

### Unique job identity

Assert database constraint prevents duplicate:

```text
source_connection_id + external_job_id
```

### Current version uniqueness

Assert no job may have two current versions.

### Quarantine

Invalid record produces:

```text
quarantine record
```

without creating an invalid job.

---

## 37. Required End-to-End Fixture Test

Run:

```text
jobs_v1
↓
jobs_v1
↓
jobs_v2
```

Expected:

### After first run

```text
jobs_new > 0
job_versions = one per job
```

### After second run

```text
jobs_new = 0
jobs_changed = 0
all valid jobs unchanged
no extra job versions
```

### After third run

```text
only modified jobs receive new versions
unmodified jobs remain unchanged
```

This test is one of the most important Phase 1 acceptance tests.

---

## 38. R2 Integration Test

Provide at least one integration test or manual test procedure that verifies:

```text
payload uploaded
object exists
retrieved payload matches uploaded bytes
```

Do not require real R2 for the main test suite.

Use environment-gated integration testing.

Example:

```text
RUN_R2_INTEGRATION_TESTS=true
```

---

## 39. Alembic Requirements

Phase 1 must include:

- initial database migration;
- downgrade support where practical;
- documented migration command.

Expected commands:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
```

The initial migration should create:

```text
companies
source_connections
pipeline_runs
raw_snapshots
source_observations
jobs
job_versions
quarantine_records
```

plus required constraints and indexes.

---

## 40. Seed Command

Provide a development seed command that can create:

```text
sample company
sample Greenhouse source connection
```

Usage:

```bash
uv run python -m app.cli.seed_dev <greenhouse-board-token>
```

The command is idempotent for the same provider and board token. Optional
`--company-name` and `--company-slug` arguments control the development company.

Do not seed fake job versions if ingestion fixtures can generate them naturally.

---

## 41. Environment Variables

At minimum:

```text
APP_ENV
LOG_LEVEL

DATABASE_URL

OBJECT_STORAGE_BACKEND

R2_ENDPOINT_URL
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME

LOCAL_STORAGE_PATH

HTTP_CONNECT_TIMEOUT_SECONDS
HTTP_READ_TIMEOUT_SECONDS
```

`.env.example` must contain placeholders only.

---

## 42. Code Quality Requirements

Use:

- Ruff;
- pytest;
- static type checking where practical;
- Pydantic v2;
- SQLAlchemy 2-style patterns;
- Alembic.

Avoid:

- untyped dictionaries flowing through the entire application;
- catch-all `except Exception` without logging/re-raising strategy;
- business logic inside route handlers;
- direct boto/R2 usage scattered across modules;
- Greenhouse-specific fields inside generic job services.

---

## 43. Domain Separation Requirement

Dependencies should generally flow like:

```text
API / CLI
    ↓
Application service
    ↓
Domain/pipeline logic
    ↓
Repositories/interfaces
    ↓
Infrastructure
```

Source-specific adapter:

```text
Greenhouse
    ↓
Canonical model
```

not:

```text
Generic job service
    ↓
Greenhouse-specific JSON access
```

---

## 44. Error Categories

Implement stable internal error categories.

At minimum:

```text
SOURCE_CONFIGURATION_ERROR
SOURCE_REQUEST_FAILED
SOURCE_RESPONSE_INVALID
RAW_STORAGE_FAILED
RECORD_VALIDATION_FAILED
NORMALIZATION_FAILED
DATABASE_WRITE_FAILED
SOURCE_SYNC_ALREADY_RUNNING
PIPELINE_INTERNAL_ERROR
```

These should be usable in:

- logs;
- pipeline-run records;
- API responses;
- tests.

---

## 45. Definition of Done

Phase 1 is complete only when all of the following are true.

### Infrastructure

- PostgreSQL runs locally;
- migrations apply successfully;
- migrations can be rolled back where supported;
- local raw storage works;
- R2 adapter exists and has been tested.

### Greenhouse

- configured source can be fetched;
- raw response is preserved;
- source errors are categorized;
- malformed records do not crash valid-record ingestion.

### Persistence

- canonical jobs persist;
- stable job uniqueness is enforced;
- versions persist;
- only one current version exists per job;
- observations persist;
- quarantine records persist.

### Idempotency

- ingesting identical data twice creates no duplicate jobs;
- identical data creates no duplicate versions.

### Versioning

- changed canonical content creates a new version;
- old versions remain available;
- effective timestamps are updated correctly.

### Lineage

A job version can be traced to:

```text
source observation
→ pipeline run
→ raw snapshot
→ R2/local object key
```

### Observability

Pipeline runs expose:

```text
records fetched
records valid
records quarantined
jobs new
jobs changed
jobs unchanged
status
duration
```

### Tests

- unit tests pass;
- integration tests pass;
- fixture pipeline test passes;
- type/lint checks pass.

### Documentation

README includes:

- local setup;
- migration instructions;
- seed instructions;
- pipeline-run command;
- test command.

---

## 46. Phase 1 Demo Scenario

The completed Phase 1 should be demonstrable without a frontend.

Example:

```bash
docker compose up -d postgres

uv run alembic upgrade head

uv run python -m app.cli.seed_dev <greenhouse-board-token>
```

Then:

```bash
uv run python -m app.cli.sync_source <source-id>
```

Output:

```text
Pipeline completed

Provider: Greenhouse
Fetched: 8
Valid: 8
Quarantined: 0

New: 8
Changed: 0
Unchanged: 0

Raw snapshot:
bronze/greenhouse/.../jobs.json
```

Run again:

```text
Fetched: 8
New: 0
Changed: 0
Unchanged: 8
```

Then process a modified fixture:

```text
Fetched: 8
New: 0
Changed: 2
Unchanged: 6
```

Inspect the run through the administrative API:

```http
GET /api/v1/pipeline-runs/{run-id}
```

Job-version history is verified through PostgreSQL integration tests in Phase 1;
a public job-history endpoint is outside this phase.

---

## 47. What the Developer Must Understand Before Phase 2

Before moving forward, the developer should be able to explain:

1. Why raw responses go to R2.
2. Why PostgreSQL does not replace raw storage.
3. Why `jobs` and `job_versions` are separate.
4. Why every successful observation does not create a version.
5. What makes ingestion idempotent.
6. What the content hash represents.
7. Why `last_seen_at` must not participate in the version hash.
8. Why a failed source run cannot mark jobs closed.
9. What quarantine means.
10. How a normalized job version traces back to raw source data.
11. Why provider-specific mapping belongs outside the jobs domain.
12. Why scheduling is separate from pipeline logic.
13. Why Phase 1 does not need Kafka, Spark, Redis, or Airflow.

If these cannot be explained clearly, review Phase 1 before expanding the architecture.

---

## 48. Phase 1 Completion Gate

Do not begin Phase 2 merely because:

```text
the Greenhouse API call works
```

Phase 1 passes only when:

```text
Fetch
→ Preserve
→ Validate
→ Normalize
→ Persist
→ Re-ingest safely
→ Detect change
→ Preserve history
→ Trace lineage
→ Report pipeline health
```

works as one coherent pipeline.

That pipeline becomes the foundation for every later source, enrichment process, dashboard, alert, and analytical dataset in OpenRole.
