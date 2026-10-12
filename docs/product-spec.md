# OpenRole Observatory — Product Specification

## Product problem

Employer job listings change or disappear without leaving a reliable public
history. Aggregators may be stale, transform source data opaquely, or make it
impossible to trace a normalized listing back to the employer's original ATS
response.

OpenRole Observatory builds a trustworthy job-data foundation by collecting
public employer ATS data, preserving the exact source response, normalizing it
into a stable model, and retaining observable history.

## Primary users

Phases 1–3 serve the developer/operator who configures sources, runs ingestion,
and inspects pipeline health. Phase 4 adds a separate read-only experience for
job seekers to discover listings, inspect source freshness and review recent
material changes. Observation remains evidence of source presence rather than
confirmation that an employer is hiring.

## Product principles

- Preserve source evidence before transformation.
- Prefer direct employer ATS data over third-party copies.
- Keep normalized records traceable to their source observation and raw bytes.
- Treat unchanged ingestion as an observation, not a new version.
- Preserve historical versions instead of overwriting them.
- Isolate malformed individual records and keep processing valid records.
- Fail visibly when the source response or infrastructure is unusable.
- Add infrastructure only when a demonstrated requirement needs it.

## Greenhouse source automation increment

The post-Phase-4 requested increment discovers Greenhouse board candidates from
the CC0 public ATS directory, verifies each new board through official metadata,
and registers at most 25 new boards per cycle. Native board names and preserved
raw discovery evidence support registration; the ordinary ingestion pipeline
remains responsible for canonical listings, versions, observations and lifecycle.
The external scheduler triggers at 00:00/06:00/12:00/18:00 Asia/Manila and refreshes
all active Greenhouse sources. Existing disabled sources are never reactivated.
Failures and catalogue omissions never imply job removal. Coverage follows the
verified catalogue, without guaranteeing every Greenhouse board or a monitoring
SLA. No other provider, public write endpoint or background queue is added.
See [source-automation.md](source-automation.md) and
[ADR 0003](adrs/0003-greenhouse-source-automation.md). Phase scope below is historical.

## Deployment preparation increment

The selected topology is Render API/cron and Vercel frontend. The single operator
uses dashboard HTTP Basic credentials; server-side administrative API calls use a
separate bearer token. Production administrative access fails closed when
credentials are missing. Public listing reads remain unauthenticated. This adds
no user accounts or changes to ingestion/lifecycle behavior. Earlier phase scope
and completion reports below remain historical. See
[ADR 0004](adrs/0004-render-vercel-administrative-access.md) and the
[deployment guide](deployment-render-vercel.md). Actual hosted verification is pending.

## Phase 1 product scope

Phase 1 supports one configured public Greenhouse source at a time through a
manual CLI or restricted administrative API. A synchronization:

1. creates an observable pipeline run;
2. fetches the Greenhouse job-board response;
3. stores the exact response bytes in filesystem storage or Cloudflare R2;
4. records raw-snapshot metadata in PostgreSQL;
5. validates source records and maps valid records to the canonical job model;
6. classifies each record as new, unchanged, or changed;
7. persists stable jobs, immutable versions, and source observations;
8. quarantines malformed individual records; and
9. records final status and metrics.

The delivered administrative surface is:

```text
GET  /health
GET  /ready
POST /api/v1/sources/{source_id}/sync
GET  /api/v1/pipeline-runs
GET  /api/v1/pipeline-runs/{run_id}
```

These endpoints have no application authentication in Phase 1 and must be
protected by a private network, reverse-proxy access policy, platform
authentication, or equivalent external control.

## Phase 1 success criteria

- A clean PostgreSQL database can be migrated using Alembic alone.
- A Greenhouse source can be configured and synchronized end to end.
- Exact raw bytes exist before canonical processing begins.
- Re-ingesting identical content creates observations but no duplicate jobs or
  job versions.
- Material canonical changes create new versions without modifying old ones.
- Invalid child records are recoverable through quarantine and Bronze lineage.
- Source, storage, and top-level validation failures produce failed runs.
- Operators can inspect health, readiness, run status, and run metrics.
- Normal automated tests require neither live Greenhouse nor R2 credentials.

## Delivered Phase 2 scope

Phase 2 adds persisted field changes, conservative absence confirmation after
two safe missing observations, tentative reset, reappearance, and administrative
job/version/change/lifecycle/source-health inspection. Failed or incomplete
source evidence never advances absence decisions. Normal sync commits lifecycle
changes with successful run finalization; canonical ingestion remains separately
durable. Timestamps describe OpenRole observations rather than exact employer
actions. The APIs retain the external access-control requirement above.

See [phase-2-completion.md](phase-2-completion.md) for verification and limitations.

## Phase 3: internal operational dashboard

The internal Next.js dashboard replaces the abandoned Multi-ATS Phase 3 direction.
Greenhouse remains the only implemented provider. It exposes Overview, Jobs,
Job Detail, Pipeline Runs, Run Detail, Quarantine, Quarantine Detail, Sources, and
Source Detail through typed server-side FastAPI reads. Job Detail uses stored
versions, field changes, and lifecycle events; it does not reconstruct domain
history. Runs expose persisted statuses and metrics, with backend status/source
filters. No aggregate job metrics or unsupported provenance fields are invented.

Source Detail provides one administrative write action: manual synchronization
through the existing synchronous FastAPI endpoint. Local pending protection and
the backend source lock prevent concurrent submission. Result feedback and refresh
use authoritative persisted outcomes. Partial record errors remain distinct from
failed synchronization. No polling, scheduler, queue, source CRUD, authentication,
or public search product is introduced.

Description HTML is sanitized before rendering; source configuration/account keys
remain excluded. The dashboard must stay local or externally access-controlled,
especially its write action. See [phase-3.md](phase-3.md) for final contracts and
[phase-3-completion.md](phase-3-completion.md) for tested evidence and limitations.
The separate [Phase 4 public product](phase-4.md) adds landing, discovery and
detail routes through dedicated public-safe contracts. It does not publish the
operational dashboard or authorize exposing administrative APIs.

## Delivered Phase 4 scope

Public routes `/`, `/jobs` and `/jobs/{jobId}` provide backend-driven literal
search, location/workplace/employment filters, bounded pagination, observation
timestamps, source evidence, safe original-listing links and sanitized current
descriptions. Recent changes are a curated projection of accepted persisted
events: salary changes are grouped, description changes disclose only a marker,
and operational provenance/configuration remains private.

Historical not-observed listings remain addressable but are excluded from
discovery and sitemap promotion. Metadata, canonical URLs, robots and a runtime
sitemap use an explicitly configured site origin; absent configuration disables
indexing. JobPosting JSON-LD is deferred because required employer publication
facts are unavailable. See [the Phase 4 completion report](phase-4-completion.md)
for final verification, deployment prerequisites and concrete limitations.

## Phase 1 non-goals

Phase 1 does not include a frontend, public job-search API, authentication,
users, billing, alerts, additional ATS providers, removal or reappearance
detection, scheduling infrastructure, background workers, analytics products,
AI enrichment, or field-level change events.

## Data-layer terminology

- **Bronze:** immutable provider-native response bytes in object storage.
- **Silver:** validated canonical operational records in PostgreSQL.
- **Gold:** future analytical or user-facing datasets; not implemented in
  Phase 1.

Detailed system behavior lives in [architecture.md](architecture.md), database
semantics in [data-model.md](data-model.md), and the Phase 1 implementation
contract in [phase-1.md](phase-1.md).
