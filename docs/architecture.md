# OpenRole Observatory - Architecture

## 1. Purpose

This document defines the initial system architecture for OpenRole Observatory.

The architecture is designed around four priorities:

1. preserve original job-source data before transformation;
2. keep normalized application data queryable and traceable;
3. make ingestion replayable and observable;
4. keep infrastructure simple enough for a solo developer while preserving a clear path for future growth.

The initial system is intentionally not distributed across many services.

OpenRole should begin as a modular Python application with:

- FastAPI;
- PostgreSQL;
- Cloudflare R2;
- manually triggered ingestion jobs, with scheduling kept as an external concern;
- source-specific connectors;
- deterministic normalization and change detection.

Additional infrastructure such as Prefect, dbt, Redis, Kafka, Spark, Elasticsearch, or separate worker platforms should only be introduced when a concrete requirement justifies them.

---

## 2. High-Level Architecture

The initial data flow is:

```text
                    Public ATS Sources
                  Greenhouse / future ATS
                           │
                           ▼
                    Source Connector
                           │
                           ▼
                     Fetch Response
                           │
                 ┌─────────┴──────────┐
                 │                    │
                 ▼                    ▼
          Cloudflare R2          Pipeline Run
           Raw / Bronze          Metadata
                 │                    │
                 └─────────┬──────────┘
                           ▼
                       Validation
                           │
                ┌──────────┴──────────┐
                │                     │
                ▼                     ▼
             Valid                Invalid
                │                     │
                ▼                     ▼
          Normalization           Quarantine
                │
                ▼
           PostgreSQL
         Silver / Canonical
                │
                ▼
        Change Detection
                │
         ┌──────┴────────┐
         │               │
         ▼               ▼
    Current State     Job History
         │               │
         └───────┬───────┘
                 ▼
              FastAPI
                 │
                 ▼
            Future Clients

       Next.js / Public API / Webhooks
```

Phase 3 implements the internal Next.js client described below. Phase 4 Task 43
adds the dedicated public jobs read boundary. Task 44 adds a static public landing
page and header/main/footer shell. Task 45 replaces `/jobs` with server-rendered
public discovery, native GET filters and backend-driven pagination. Task 46 adds
server-rendered current public detail, request-shared metadata, lifecycle evidence
and the shared sanitized description path. Task 47 adds a curated recent-change
projection over persisted JobChangeEvents and a secondary public detail section.
Task 48 adds configured metadata/canonicals, lifecycle indexing, robots and a
dynamic sitemap backed by a tiny public ID cursor query. JobPosting markup is
deferred for missing publication facts. Full public version/lifecycle history and
webhooks remain future work. Task 49 verifies the complete public journey,
public/internal separation, sanitization, pagination, SEO, accessibility and
runtime failures without changing schema or pipeline behavior. See
[the Phase 4 completion report](phase-4-completion.md). Public reads currently
use deliberate uncached server requests at the small deployment scale; this
does not provide real-time source monitoring. The later Render/Vercel deployment
increment implements dashboard Basic authentication and a separate administrative API bearer guard; see
[ADR 0004](adrs/0004-render-vercel-administrative-access.md). Hosted enforcement
and production infrastructure still require verification before launch.

The application must preserve the distinction between:

```text
Source data
Normalized data
Derived data
User-facing data
```

These layers may contain similar information but have different responsibilities.

---

## 3. Architectural Style

OpenRole should initially use a:

> Modular monolith with explicit domain boundaries.

This means:

- one primary backend codebase;
- one PostgreSQL database;
- one object-storage service;
- one deployment unit for the API;
- one or more scheduled pipeline processes using the same application modules.

A modular monolith is preferred over microservices because the initial system does not require independent scaling, independent deployments, or separate engineering teams.

The codebase should still enforce boundaries between concerns so that components may later be separated if justified.

Major modules include:

```text
sources
ingestion
storage
jobs
companies
pipeline_runs
quarantine
events
api
shared
```

Source-specific logic must not leak into unrelated modules.

For example:

```text
Greenhouse-specific field mapping
```

belongs inside the Greenhouse source adapter.

It should not appear inside:

```text
jobs service
search logic
dashboard logic
```

---

## 4. Core Components

### 4.1 Source Connector Layer

The source connector layer retrieves job data from external ATS systems.

Phase 1 supports:

```text
Greenhouse
```

Future connectors may include:

```text
Lever
Ashby
Workable
Custom supported career sources
```

Each connector should expose a consistent interface.

Conceptually:

```python
class JobSourceConnector:
    async def fetch_jobs(
        self,
        source_config: SourceConfig,
    ) -> SourceFetchResult:
        ...
```

The connector is responsible for:

- constructing requests;
- authentication where required;
- pagination;
- timeout handling;
- provider-specific response parsing;
- source-level metadata;
- provider-specific errors.

The connector must not perform canonical job normalization.

That responsibility belongs to the mapping layer.

This separation allows:

```text
Fetch source data
```

and:

```text
Interpret source data
```

to evolve independently.

For Greenhouse, the HTTP client translates the source connection's
`external_account_key` into the public board token and calls:

```text
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
```

The client returns the exact response bytes, HTTP status, content type, and UTC
retrieval time. It uses explicit connect/read timeouts and at most three attempts.
Transport failures plus HTTP 429, 500, 502, 503, and 504 are retryable; other 4xx
responses are not. Numeric `Retry-After` values are bounded before use.

The caller owns and may reuse the injected `httpx.AsyncClient`. The transport
client does not parse jobs, persist pipeline state, write object storage, or mutate
source connections. A streaming response-size limit and HTTP-date-form
`Retry-After` handling are deferred until operational evidence justifies them.

---

### 4.2 Source Mapping Layer

Each provider uses its own schema.

The mapping layer converts a validated provider record into the OpenRole canonical representation.

Example:

```text
Greenhouse payload
        ↓
Greenhouse mapper
        ↓
Canonical job input
```

Future:

```text
Lever payload
        ↓
Lever mapper
        ↓
Canonical job input
```

The mapper is responsible for:

- field-name translation;
- source-specific null handling;
- source date conversion;
- basic location normalization;
- source URL extraction;
- source-specific metadata preservation;
- canonical field construction.

The mapper must not silently invent information.

Example:

If Greenhouse does not explicitly identify workplace type:

```text
workplace_type = null
```

is preferable to guessing:

```text
remote
```

from arbitrary description text.

Enrichment can occur in later processing stages.

---

## 5. Raw Data Storage - Bronze Layer

Cloudflare R2 stores immutable raw source responses.

The purpose of raw storage is to preserve:

> What did the source actually return during this ingestion run?

This enables:

- replaying transformations;
- investigating parser bugs;
- comparing source behavior;
- rebuilding normalized data;
- demonstrating data lineage;
- debugging schema changes.

Raw objects should not be modified after creation.

If the same source is retrieved twice, each ingestion run should receive its own raw snapshot.

---

### 5.1 Proposed R2 structure

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

Example:

```text
bronze/
  greenhouse/
    0199abcd-.../
      year=2026/
        month=09/
          day=28/
            run=0199abcd-.../
              jobs.json
```

This object path provides:

- source;
- internal source-connection identity;
- date partition;
- pipeline-run lineage.

The path must use sanitized internal identifiers rather than arbitrary user-provided path segments.

---

### 5.2 Raw object metadata

Each raw object should have associated metadata stored in PostgreSQL.

The metadata table is:

```text
raw_snapshots

id
pipeline_run_id
r2_object_key
retrieved_at
content_hash
record_count
content_type
content_length_bytes
```

The database should reference R2.

R2 should not be treated as the system for querying application state.

During raw acquisition, OpenRole first validates the running pipeline run and
its persisted source configuration in a short database read. The Greenhouse
request and object-storage write then happen without an open database
transaction. A final short transaction locks and revalidates the run before
creating its one `raw_snapshots` row. The unmodified HTTP response bytes are
stored; `record_count` remains null until later parsing.

Object storage and PostgreSQL do not share a transaction. If the object write
succeeds but metadata persistence fails, the error is surfaced and the stored
key is logged as a possible orphan. Phase 1 does not add deletion to the shared
storage contract solely for compensation. A retry uses the same deterministic
key and can therefore encounter an immutable-object conflict until an operator
reconciles the orphan.

Stored snapshots are replayed through the same provider-neutral object-storage
interface. Before decoding, processing verifies the retrieved bytes against the
snapshot's SHA-256 hash and stored length. Invalid JSON or an invalid Greenhouse
envelope fails the whole processing stage; once a valid `jobs` array exists,
each child record is validated independently.

All valid `SourceObservation` rows and the snapshot's total `record_count` are
written in one short transaction after validation. Invalid child records are
returned as typed results for later quarantine persistence and do not create
observations. Array positions produce diagnostic locators such as `jobs[3]`,
while stable identity remains the source connection plus external job ID.
Reprocessing is rejected when `record_count` is already known or observations
already reference the snapshot, including the successful empty-board case where
`record_count` is zero.

---

## 6. PostgreSQL - Silver Layer

PostgreSQL stores normalized and operational records.

It should answer questions such as:

- What companies are configured?
- What jobs are currently known?
- What is the current version of a job?
- When was the job first observed?
- When was it last observed?
- What historical versions exist?
- Which pipeline run produced this version?
- Which records failed normalization?

PostgreSQL should not store the raw source payload as the only copy of source data.

Large raw responses belong in R2.

Small source-specific metadata may still be stored in JSONB where useful.

---

## 7. Canonical Data Model

Source-specific records should eventually map to a canonical model.

At a conceptual level:

```text
Company
   │
   ├── Source Connection
   │       │
   │       └── Source Records
   │
   └── Jobs
          │
          ├── Current Job State
          │
          └── Job Versions
```

Important distinction:

```text
Job
```

represents the stable identity of a role.

```text
JobVersion
```

represents what was observed at a point in time.

For example:

```text
Job #123

Version 1:
Remote
2 years experience

Version 2:
Hybrid
4 years experience
```

The job remains the same logical job while the observed state changes.

The exact relational schema is defined in:

```text
docs/data-model.md
```

---

## 8. Job Identity

Each source normally provides a provider-specific job identifier.

Phase 1 should primarily identify a job using a combination of:

```text
source
source organization
source job ID
```

Conceptually:

```text
greenhouse
+
company_123
+
job_456
```

This produces a stable source identity.

Do not attempt semantic cross-source job deduplication in Phase 1.

For example:

```text
Greenhouse job 456
```

and:

```text
Lever job XYZ
```

must not automatically be considered the same job even if their titles are identical.

Cross-source entity resolution belongs to a later phase.

---

## 9. Content Hashing

Normalized job state should be hashed so the pipeline can quickly determine whether meaningful source content changed.

Conceptually:

```text
normalized fields
        ↓
stable serialization
        ↓
SHA-256
        ↓
content_hash
```

Only fields representing observed job content should contribute to the version hash.

Operational metadata should not.

For example:

These SHOULD influence the hash:

```text
title
description
location
employment type
workplace type
salary
source URL
```

These SHOULD NOT:

```text
last_seen_at
pipeline_run_id
database ID
updated_at in OpenRole
```

Otherwise every observation would incorrectly create a new version.

The exact hash input should be documented and tested.

---

## 10. Ingestion Pipeline

The Phase 1 pipeline should follow a predictable sequence.

```text
1. Acquire the per-source execution lock
2. Load and validate the source configuration
3. Create the pipeline run and mark it running
4. Fetch source
5. Store raw response
6. Validate source response
7. Iterate through source records
8. Validate individual record
9. Normalize record
10. Resolve stable job identity
11. Compare with current state
12. Insert or update state
13. Create version when required
14. Update last-seen timestamp
15. Record quarantine failures
16. Calculate pipeline metrics
17. Finish the pipeline run
18. Release the source execution lock
```

Each stage should produce observable outcomes.

Phase 2 Task 31 extends the record-processing stage with presence validation and
lifecycle reconciliation before terminal finalization. SourceSyncService invokes
present-state reconciliation, prior-absence confirmation, and new first-absence
detection in that order while the source lock remains held. It owns terminal
status for the full sync; SnapshotIngestionOrchestrator's `process_records()`
returns metrics without finalizing. Its standalone `process_snapshot()` entry
point retains Phase 1 finalization behavior for compatibility.

Record processing supplies an internal typed handoff for validating a still-running
run against snapshot counts and durable observations/quarantine. Unsafe membership
skips lifecycle work without failing valid ingestion. Task 33 makes presence
validation, all three lifecycle stages, and successful finalization share one
short database transaction. Lifecycle fields/events, terminal status/metrics, and
the successful-sync timestamp commit together. Stage or commit failure rolls
them back before failed-run finalization in a separate transaction. The source
lock remains held through both paths. Earlier canonical record transactions may
already be committed; no database transaction spans HTTP or object-storage I/O.
Standalone lifecycle/finalization calls still own their transactions. See
[ADR 0001](adrs/0001-atomic-lifecycle-finalization.md).

The source execution lock is a session-level PostgreSQL advisory lock derived
deterministically from the source connection UUID. It is owned by one dedicated
database connection for the execution scope. Run creation, state transitions,
metric persistence, and source timestamp updates use separate short
transactions; future source HTTP calls and object-storage writes must not occur
inside a long-lived database transaction. Cleanup releases the lock on both
normal and exceptional exits. Lock contention does not create a pipeline-run
record.

---

## 11. Pipeline Run Model

Every ingestion execution must have a persistent run record.

Example:

```text
pipeline_runs

id
source_id
status
started_at
completed_at

records_fetched
records_valid
records_invalid

jobs_new
jobs_changed
jobs_unchanged

raw_object_key

error_code
error_summary
```

Possible statuses:

```text
pending
running
completed
completed_with_errors
failed
```

The pipeline run provides operational visibility and debugging context.

A failed run should not be indistinguishable from:

```text
source returned zero jobs
```

Those are very different conditions.

---

## 12. Idempotency

Repeated ingestion of the same source state must not produce duplicate logical jobs or duplicate versions.

Example:

First run:

```text
Job source ID: 1001
Title: Backend Engineer
Location: Berlin
```

Result:

```text
Job created
Version 1 created
```

Second identical run:

```text
Job source ID: 1001
Title: Backend Engineer
Location: Berlin
```

Result:

```text
Existing job located
No new version created
last_seen_at updated
```

Third changed run:

```text
Job source ID: 1001
Title: Backend Engineer
Location: Berlin — Hybrid
```

Result:

```text
Existing job located
Version 2 created
Current version updated
```

Idempotency should be enforced through:

- database uniqueness constraints;
- stable source identifiers;
- content hashes;
- transaction boundaries.

It should not rely only on application-level `if` checks.

---

## 13. Transactions

Each normalized record should be persisted within an explicit database transaction.

A failure while processing one job should not necessarily invalidate all successfully processed jobs in a large ingestion run.

The pipeline should support record-level failure isolation.

Conceptually:

```text
Pipeline run

Job A → success
Job B → success
Job C → normalization failure → quarantine
Job D → success
```

The overall result may become:

```text
completed_with_errors
```

rather than:

```text
failed
```

However, failures affecting the source as a whole should fail the run.

Examples:

```text
ATS endpoint unavailable
Invalid source configuration
R2 unavailable before raw response is preserved
Database unavailable
Unexpected top-level schema
```

---

## 14. Quarantine Architecture

Invalid records must not be silently ignored.

Quarantine records should preserve:

- pipeline run;
- source provider;
- source job ID if available;
- error category;
- error message;
- raw record reference;
- time quarantined.

Example categories:

```text
schema_validation_failed
normalization_failed
unsupported_value
missing_required_identifier
invalid_timestamp
unexpected_source_shape
```

The raw record itself may remain inside the R2 run snapshot.

The quarantine record should identify where that source data can be retrieved.

Future tooling may allow records to be replayed after fixing a transformation.

---

## 15. Source Failure Handling

The system must distinguish between:

```text
No jobs returned successfully
```

and:

```text
Source could not be checked
```

If Greenhouse returns an error:

```text
HTTP 500
timeout
DNS failure
unexpected schema
```

OpenRole must not assume that existing jobs were removed.

Therefore:

> A failed ingestion must never be interpreted as job closure.

Only successful observations may contribute to disappearance detection.

This becomes especially important in later phases.

---

## 16. Removal Detection

Phase 1 should establish the timestamps needed for removal detection, but conservative behavior is preferred.

Every active job should track:

```text
first_seen_at
last_seen_at
```

When a successful source run completes and a previously observed job is absent, the system may record it as:

```text
not observed in latest successful run
```

Future phases may introduce confirmation strategies such as:

- absent from multiple consecutive successful runs;
- direct job endpoint returns 404;
- source-specific closure indicator.

The architecture should not automatically classify temporary source failures as job removal.

---

## 17. Reappearance

The system should eventually support:

```text
active
→ no longer observed
→ observed again
```

This should not create a completely unrelated job if the source job identifier remains stable.

Instead, the job lifecycle should record reappearance.

Possible future event:

```text
job.reappeared
```

The historical versions and lifecycle should remain connected.

---

## 18. Scheduling

Phase 1 does not require a dedicated orchestration platform.

The ingestion command should be executable directly:

```bash
uv run python -m app.cli.sync_source <source-id>
```

or equivalent.

It may initially be scheduled through:

- cron;
- Render Cron Job;
- GitHub Actions;
- another basic scheduler.

The pipeline logic must not be embedded inside the scheduler.

The requested post-Phase-4 increment implements this boundary with
`app.cli.automate_greenhouse` and an external systemd timer. A bounded catalogue
reader supplies only candidate tokens; official Greenhouse board metadata and
raw ObjectStorage evidence precede short, idempotent registration transactions.
The CLI then calls the existing SourceSyncService for every active Greenhouse
source. A reserved advisory-lock scope prevents overlapping automation cycles;
the existing per-source locks protect manual sync overlap. No database transaction
spans network or object-storage calls. See [source automation](source-automation.md)
and [ADR 0003](adrs/0003-greenhouse-source-automation.md) for precise boundaries,
admission limits and failure handling.

The scheduler is responsible only for:

```text
when to run
```

The application is responsible for:

```text
what the ingestion run does
```

This allows future migration to Prefect or another orchestrator without rewriting the pipeline.

---

## 19. Future Orchestration

A workflow orchestrator may become useful when OpenRole requires:

- many ATS connectors;
- hundreds or thousands of companies;
- task dependencies;
- backfills;
- retry visibility;
- concurrency controls;
- scheduled partition processing;
- richer observability.

At that stage, Prefect or Dagster may be evaluated.

Airflow should not be introduced merely because it is commonly associated with data engineering.

The orchestration tool should solve an actual operational problem.

---

## 20. FastAPI Role

FastAPI is the serving and administrative API layer.

It should not contain the core pipeline implementation directly inside route handlers.

Example administrative endpoint:

```http
POST /api/v1/sources/{source_id}/sync
```

The route should:

```text
validate request
↓
authorize request
↓
invoke pipeline application service
↓
return run identifier
```

The route should not contain:

```text
Greenhouse HTTP logic
R2 upload logic
normalization logic
database transformation logic
```

Those belong to dedicated modules.

---

## 21. Initial API Responsibilities

FastAPI will eventually expose:

```text
GET /api/v1/jobs
GET /api/v1/jobs/{job_id}
GET /api/v1/jobs/{job_id}/versions

GET /api/v1/companies
GET /api/v1/companies/{company_id}

GET /api/v1/pipeline-runs
GET /api/v1/pipeline-runs/{run_id}

POST /api/v1/sources/{source_id}/sync
```

Phase 1 exposes only the required health, readiness, pipeline-run inspection,
and source-sync administrative endpoints. Phase 2 now adds read-only job detail,
version, field-change, lifecycle, and source-health inspection endpoints. Typed
read schemas and focused JobQueryService/SourceQueryService projection queries
keep SQL and ORM relationships out of routes. Change queries join only version
numbers; histories are bounded and ordered deterministically. No GET invokes
ingestion or lifecycle mutation. These endpoints retain the same external
access-control requirement as the Phase 1 administrative API.

Phase 4 Task 43 adds `GET /api/v1/public/jobs` and
`GET /api/v1/public/jobs/{job_id}` through a separate PublicJobQueryService and
explicit public Pydantic schemas. Joined scalar projections select current
canonical content, company display fields and provider without loading operational
entities, configuration or metadata. Discovery requires observed jobs from active
sources; detail retains known historical jobs. Search/filter/count/page work runs
in PostgreSQL, using existing indexes and current-version constraints. Public
routes share the existing error envelope but expose generic read-invariant errors.
Descriptions remain untrusted source HTML. Task 46 sanitizes them in the shared
server-side description renderer before public presentation; public page/metadata
read only this API, sharing one read per request without cross-request caching.
Descriptions that start with entity-encoded markup are decoded by one outer layer
before the shared allowlist sanitizer. Safe div blocks retain source paragraph
structure. Native HTML and plain text keep their existing semantics, including
escaped examples within native HTML. Decoding never follows sanitization, and
this presentation step does not mutate canonical hashes or stored history.
No ingestion transaction, schema, admin contract, authentication or CORS behavior
changes. See [the delivered contract](phase-4.md#task-43-delivered-public-api-contract).

### Phase 3 Task 34: Next.js dashboard boundary

The internal dashboard lives in `frontend/`, alongside the unchanged Python
backend. Its App Router pages and persistent dashboard layout use server
components. Small client components handle active navigation, the mobile drawer,
and error retry. The server-only typed API client reads `OPENROLE_API_BASE_URL`
and calls FastAPI using native fetch with a bounded timeout and `cache: no-store`.
Only `/health` and `/ready` are consumed in Task 34; status failures are handled
independently so the shell remains usable during an outage.

```text
Browser → Next.js server → typed API client → FastAPI → PostgreSQL readiness probe
```

Next.js does not connect to PostgreSQL or object storage, reproduce ingestion or
lifecycle rules, or implement duplicate API routes. Server-side requests need no
browser CORS configuration. Jobs, Sources, Pipeline Runs, and Quarantine remain
placeholder routes. [ADR 0002](adrs/0002-internal-dashboard-api-boundary.md) records
this frontend decision; [frontend/README.md](../frontend/README.md) explains setup.

Task 35 extends the overview with dedicated server-side source-health and
pipeline-run reads. A small orchestration function settles independent requests
concurrently; a failed section does not suppress successful sections. The same
ApiClient/ApiError and runtime-validation approach is reused, with uncached reads
and the existing timeout. Five recent runs are requested across all sources.

At Task 35 delivery the backend had no source-list or aggregate job-count
endpoint. One optional
`OPENROLE_DEFAULT_SOURCE_ID` selects a source for development monitoring; the
frontend neither discovers sources from recent runs nor reads PostgreSQL.
Missing configuration produces a monitoring empty state, while endpoint failures
produce section error states. Presentation helpers format UTC timestamps,
server-rendered relative time, run duration, and status labels. They do not
calculate lifecycle state, freshness thresholds, or ingestion decisions.

Task 36 adds `GET /api/v1/jobs` and a server-rendered Jobs explorer. The query
service uses three reads independent of page size: check for missing current
versions in the selected identity/lifecycle/source scope, count using the list's
exact filters, and fetch scalar display fields joined with the current version,
company, and source. No ORM relationship is lazily loaded and canonical
descriptions/configuration are excluded. The existing partial unique index
ensures at most one current version; a missing current version produces a safe
500 invariant error, even if canonical search or pagination would hide that job.

URL state (`page`, `status`, `source`, `q`) is validated in the Next.js server
page; the API validates its own parameters. Client filter controls update the
URL, while PostgreSQL performs filtering and limit/offset pagination. Ordering
is `last_seen_at DESC, job.id ASC`. Total and rows are separate reads under the
existing PostgreSQL isolation level; concurrent ingestion can change the data
between reads or page visits. Offset pagination is an internal inspection tool,
not a stable snapshot. Full-text search/indexes and public ranking are deferred.


Task 39 adds `GET /api/v1/quarantine` and `GET /api/v1/quarantine/{record_id}`.
The list counts matching records and fetches one bounded scalar projection joined
to source/company display fields, using two queries regardless of page size.
The detail fetches the persisted diagnostics and the same display provenance in
one query. Neither path accesses object storage, loads raw payloads, or mutates
records. No schema change is required. Source configuration and storage object
keys are excluded; the RawSnapshot UUID retains the lineage reference.

The Quarantine pages validate URL state (`page`, `status`, `source`, `run`,
`category`) and call these APIs through the existing server-only client. Status
and category controls reset pagination; PostgreSQL applies all filters and orders
by `created_at DESC, id DESC`. Count/page reads have the same concurrency limits
as the Jobs explorer. Diagnostic messages and pretty JSON are rendered as escaped
React text. Identity notes explain potential presence evidence without computing
run safety in the browser. Quarantine links open persisted run detail, preserving
source navigation context.
Job history and run investigation use typed server-side reads.


Task 40 adds read-only source discovery and extends the existing source detail
projection with safe Company id/name/domain/careers_url fields. It preserves the
prior exclusion of configuration/account keys. `SourceQueryService` counts the
filtered source set and reads a bounded projection joined to Company and the
latest PipelineRun. A correlated scalar subquery selects that run by
`started_at DESC, id DESC`, then the outer join keeps sources without runs.
List requests use two SQL reads and detail one, independent of page size. No
source ORM object/configuration is loaded by these inspection queries.

The existing pipeline-run list now accepts an optional `source_connection_id`
UUID before pagination, preserving its existing response/defaults. Source Detail
first loads the primary source; recent runs and quarantine then settle concurrently
and independently, each requesting at most five rows. No Jobs count is derived by
loading jobs. Links reuse the Jobs/Quarantine filters and approved scoped Runs
detail routes backed by persisted resource lookups. Source active state is a
configuration fact, separate from latest-run outcome. Freshness uses persisted
attempted/successful timestamps without a frontend SLA or health score. Company
careers links accept only HTTP(S), and all source/debug text remains escaped.
At Task 40 delivery, source administration remained read-only.

Task 41 adds a client-side Sync now control to the server-rendered Source Detail
header. A Next.js Server Action validates the source identifier and forwards one
POST through the server-only API client to the existing FastAPI sync endpoint.
FastAPI retains ownership of locking, acquisition, storage, ingestion, lifecycle,
and run finalization. The browser receives safe terminal outcomes, not backend
configuration or arbitrary exception/error messages. Existing Server Action
origin protections remain enabled; no CORS change is needed.

The UI waits for synchronous completion. Mutation requests have a separate
five-minute timeout; inspection reads retain their four-second timeout. A
transport timeout does not prove backend cancellation or failure, so the UI
reports an unknown outcome and advises refreshing before another attempt.
Local pending protection complements the PostgreSQL advisory lock. Terminal
responses refresh source/latest-run/recent-run/quarantine data and invalidate
related dashboard views. Transport failures preserve the visible source and
inline error. No optimistic persisted-state changes or background infrastructure
are added. Both the dashboard and administrative API require external access
control before public exposure.

---

## 22. Storage Abstraction

Cloudflare R2 should be accessed through a storage interface rather than being referenced directly throughout the domain code.

Conceptually:

```python
class ObjectStorage:
    async def put_bytes(...): ...
    async def get_bytes(...): ...
    async def exists(...): ...
    async def delete(...): ...
```

Initial implementation:

```text
R2ObjectStorage
```

This enables:

- local development using MinIO or filesystem storage;
- easier testing;
- future migration to another S3-compatible service;
- separation between domain and infrastructure concerns.

R2's S3-compatible API makes this abstraction practical.

---

## 23. Environment Separation

The application should support at minimum:

```text
development
test
production
```

Each environment should have separate:

- database;
- R2 bucket or storage prefix;
- credentials;
- source configuration where practical.

Production data must not be used casually in automated tests.

Example object prefixes:

```text
development/bronze/...
production/bronze/...
```

Separate buckets are preferable when configuration permits.

---

## 24. Configuration

Configuration should be loaded from environment variables or an environment-specific secret store.

Examples:

```text
APP_ENV

DATABASE_URL

R2_ENDPOINT_URL
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME

HTTP_TIMEOUT_SECONDS

LOG_LEVEL
```

Secrets must never be committed.

The approved deployment-blocker Task 1 adds production-only Settings validation:
an explicit storage backend, usable PostgreSQL configuration without known
development credentials, complete HTTPS R2 settings, or an explicitly configured
absolute filesystem path for the single-host beta. Development/test defaults
remain available. Validation hides input values and settings representations
omit the database URL. Production templates contain blank secrets and real
environment files are ignored. This does not establish infrastructure readiness
or access control; see [production configuration](production-configuration.md).

Provide:

```text
.env.example
```

containing variable names but no real credentials.

---

## 25. Logging

The system should use structured logs.

A pipeline log should include context such as:

```json
{
  "event": "job_normalized",
  "pipeline_run_id": "...",
  "source": "greenhouse",
  "company_id": "...",
  "source_job_id": "12345"
}
```

Avoid logging:

- full job descriptions unnecessarily;
- secrets;
- authorization headers;
- R2 credentials;
- database credentials.

Logs should favor identifiers over full payloads.

---

## 26. Observability

Phase 1 observability can remain simple.

Required signals:

```text
pipeline run start
pipeline run finish
duration
records fetched
records validated
records quarantined
jobs new
jobs changed
jobs unchanged
source failures
storage failures
database failures
```

These metrics may initially be stored in PostgreSQL and emitted through structured logs.

A dedicated metrics platform is not required for Phase 1.

---

## 27. Error Taxonomy

Errors should be categorized rather than represented only as generic exceptions.

Example categories:

```text
SOURCE_CONFIGURATION_ERROR
SOURCE_REQUEST_FAILED
SOURCE_RESPONSE_INVALID
RAW_STORAGE_FAILED
RECORD_VALIDATION_FAILED
NORMALIZATION_FAILED
DATABASE_WRITE_FAILED
PIPELINE_INTERNAL_ERROR
```

This improves:

- monitoring;
- testing;
- quarantine analysis;
- user-facing pipeline reporting.

Unexpected exceptions should still be captured with request or run identifiers.

---

## 28. Testing Architecture

Testing should occur at multiple levels.

### Unit tests

Test isolated logic such as:

```text
Greenhouse → CanonicalJob mapping
content hash generation
date normalization
status transitions
change detection
```

Unit tests should not require external services.

---

### Integration tests

Test:

```text
SQLAlchemy + PostgreSQL
repository behavior
uniqueness constraints
transactions
pipeline persistence
```

Where practical, use a real PostgreSQL test instance rather than SQLite because database behavior differs.

---

### Connector contract tests

Use stored fixtures instead of calling Greenhouse continuously.

Example fixtures:

```text
fixtures/greenhouse/jobs_v1.json
fixtures/greenhouse/jobs_v2.json
fixtures/greenhouse/jobs_invalid_record.json
```

Tests should verify:

```text
v1 → creates jobs
v1 again → unchanged
v2 → creates expected version
invalid → quarantined
```

---

### End-to-end pipeline test

A local test should be capable of:

```text
fixture source
↓
fake/local object storage
↓
normalization
↓
PostgreSQL
↓
pipeline result
```

This verifies the complete ingestion flow without external network dependency.

---

## 29. Local Development

Local development should minimize dependence on paid services.

Recommended:

```text
FastAPI
PostgreSQL through Docker
MinIO or filesystem storage abstraction
Greenhouse fixtures
```

Cloudflare R2 should be used in development only when specifically testing R2 integration.

Developers should be able to run most tests offline.

Example:

```bash
docker compose up -d postgres
cd backend
uv run pytest
```

---

## 30. Deployment Architecture

Initial production architecture:

```text
                    Public ATS APIs
                           │
                           ▼
                  Scheduled Python Job
                           │
                    ┌──────┴──────┐
                    ▼             ▼
              Cloudflare R2     Neon
                Raw Data      PostgreSQL
                    │             │
                    └──────┬──────┘
                           ▼
                      FastAPI
                       Render
                           │
                           ▼
                   Future Next.js
                       Vercel
```

This architecture minimizes idle infrastructure cost.

No dedicated message broker is initially required.

---

## 31. Future Event Architecture

Future phases may introduce internal events such as:

```text
job.discovered
job.changed
job.no_longer_observed
job.reappeared
pipeline.completed
pipeline.failed
source.schema_changed
```

These events could drive:

- webhooks;
- email notifications;
- saved-search alerts;
- analytics updates;
- downstream integrations.

The event mechanism should initially remain internal and database-backed.

A distributed event broker should only be introduced when necessary.

---

## 32. Future Webhook Architecture

OpenRole may eventually allow external consumers to subscribe to events.

Example:

```text
job.changed
```

Payload:

```json
{
  "event_id": "evt_123",
  "event_type": "job.changed",
  "occurred_at": "2026-09-28T05:00:00Z",
  "data": {
    "job_id": "job_456",
    "changes": [
      {
        "field": "workplace_type",
        "previous": "remote",
        "current": "hybrid"
      }
    ]
  }
}
```

Webhook delivery should support:

- HMAC signatures;
- retries;
- exponential backoff;
- delivery records;
- idempotent event IDs;
- disabled failing endpoints.

Webhook implementation is not required for Phase 1.

---

## 33. Future Analytical Architecture

Later phases may introduce:

```text
R2 Bronze
    ↓
Transformation
    ↓
Parquet Silver/Gold
    ↓
DuckDB / dbt
```

Possible analytical datasets:

```text
job_lifecycle
company_hiring_activity
skill_demand
remote_work_trends
salary_coverage
international_hiring_evidence
```

This analytical pipeline should not replace PostgreSQL as the transactional serving database.

The two systems serve different workloads:

```text
PostgreSQL
→ operational queries and application API

Parquet / DuckDB
→ analytical queries and larger scans
```

---

## 34. Security Considerations

Phase 1 security requirements include:

- secrets loaded from environment variables;
- TLS for external connections;
- no secrets in logs;
- least-privilege R2 credentials;
- restricted database credentials;
- input validation for source configuration;
- sanitized storage paths;
- safe HTTP timeout configuration;
- bounded response sizes where practical.

Future authenticated administrative APIs must add:

- authentication;
- authorization;
- role-based access;
- rate limits;
- audit logging.

---

## 35. Data Retention

Raw observations are valuable for historical reconstruction, but retention should remain deliberate.

Initial recommendation:

- retain raw source snapshots while the project remains small;
- retain canonical job history indefinitely unless storage becomes problematic;
- retain quarantine records until resolved or intentionally removed;
- retain pipeline-run metadata for operational history.

Future retention policies may differ between:

```text
raw responses
normalized history
logs
quarantine records
analytics datasets
```

Deletion should preserve referential integrity and lineage where appropriate.

---

## 36. Data Lineage

Every important normalized job version should be traceable to:

```text
Job Version
    ↓
Source Record
    ↓
Pipeline Run
    ↓
R2 Raw Snapshot
```

Conceptually:

```text
job_versions.source_record_id
        ↓
source_records.pipeline_run_id
        ↓
pipeline_runs.raw_snapshot_id
        ↓
raw_snapshots.r2_object_key
```

The exact schema may differ, but this relationship must remain possible.

This is one of the central architectural requirements of OpenRole.

---

## 37. Design Decisions

The following decisions are intentional.

### R2 instead of PostgreSQL-only raw storage

Reason:

Raw API payloads are immutable blobs that do not need frequent relational queries.

R2 provides inexpensive object storage and keeps source snapshots independent of the operational database.

---

### PostgreSQL for normalized state

Reason:

OpenRole requires:

- relationships;
- unique constraints;
- transactions;
- history;
- filtering;
- API queries.

PostgreSQL is suitable for those requirements.

---

### No Kafka

Reason:

The initial pipeline volume does not justify distributed event streaming infrastructure.

---

### No Spark

Reason:

The initial dataset can be processed comfortably using Python and PostgreSQL.

---

### No Elasticsearch initially

Reason:

PostgreSQL search is sufficient until search scale or requirements demonstrate otherwise.

---

### No orchestration platform initially

Reason:

A scheduled Python command provides enough orchestration for the first connector and small number of companies.

---

### No AI in Phase 1

Reason:

The initial challenge is reliable data ingestion and history.

AI enrichment should not obscure whether the underlying data platform is correct.

---

## 38. Architectural Invariants

These rules should remain true throughout implementation.

### Invariant 1

Raw source responses are preserved before transformation whenever an ingestion run successfully retrieves them.

### Invariant 2

Source-specific schemas do not leak into the core jobs domain.

### Invariant 3

Repeated ingestion of unchanged source data does not create duplicate logical jobs or unnecessary versions.

### Invariant 4

Historical job versions are not overwritten.

### Invariant 5

A failed source request does not cause jobs to be marked closed.

### Invariant 6

Invalid records are observable and recoverable rather than silently discarded.

### Invariant 7

Important normalized data remains traceable to its source observation.

### Invariant 8

Scheduling infrastructure remains separate from pipeline business logic.

### Invariant 9

The system reports observed facts and avoids unsupported claims about employer intent.

---

### Phase 3 Task 42: investigation and closure

Job Detail reads current content first and settles versions, persisted field changes,
lifecycle events, and source information independently. HTML descriptions cross a
server-side allowlist sanitizer before rendering. Decimal salaries remain strings;
formatting does not convert them through binary floating point. Run exploration
uses optional validated status/source filters applied in PostgreSQL before ordered
pagination. Histories and runs retain their existing API shapes without totals;
bounded lookahead enables Previous/Next without fabricating counts. No schema,
ingestion, lifecycle, or transaction behavior changes. The completion report records
verification and actual limitations.

## 39. Architecture Evolution

The expected progression is:

```text
Phase 1
Greenhouse
+ R2
+ PostgreSQL
+ basic FastAPI
        ↓
Phase 2
Historical change detection
        ↓
Phase 3
Internal dashboard (Greenhouse only)
        ↓
Phase 4
Public job discovery delivered (see phase-4-completion.md)
        ↓
Phase 5
Entity resolution + deduplication
        ↓
Phase 6
Job enrichment
        ↓
Phase 7
Analytics layer
        ↓
Phase 8
Expanded product and consumer API
```

Each phase should extend the existing architecture rather than replacing the entire system.

---

## 40. Summary

OpenRole begins as a deliberately simple data platform:

```text
Fetch
→ Preserve
→ Validate
→ Normalize
→ Compare
→ Version
→ Serve
```

Cloudflare R2 preserves original source observations.

PostgreSQL stores normalized operational state and history.

Python connectors isolate ATS-specific behavior.

FastAPI exposes the resulting data and operational controls.

The architecture prioritizes:

- data provenance;
- replayability;
- idempotency;
- source isolation;
- change history;
- observability;
- simplicity.

The goal of Phase 1 is not to build a large distributed platform.

The goal is to establish a reliable data foundation that can support additional sources, analytics, APIs, and user-facing products without losing the history or provenance of the data.
