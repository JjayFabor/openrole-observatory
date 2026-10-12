# OpenRole Observatory — Phase 3: Internal Dashboard

## Direction and scope

The developer's new Task 34 request replaces the earlier proposed Multi-ATS
Phase 3 roadmap. Phase 3 now makes the existing Greenhouse system understandable
through an internal dashboard. Lever, Ashby, and other providers remain deferred.
Phases 1 and 2 are retained; their completion reports describe backend behavior.

## Final operational surfaces

Tasks 37–38 were explicitly authorized as Task 42 prerequisites and replace the
previously approved navigation placeholders. The chronological task notes below
record earlier delivery stages; this table describes the final route scope.

| Route | Current purpose |
| --- | --- |
| `/dashboard` | System readiness, monitored source, five recent runs |
| `/dashboard/jobs` | Filtered, paginated current listings |
| `/dashboard/jobs/[jobId]` | Current listing, changes, versions, lifecycle, lineage |
| `/dashboard/runs` | Status/source-filtered, newest-first run exploration |
| `/dashboard/runs/[runId]` | Persisted status, metrics, failure context, source |
| `/dashboard/quarantine` | Filtered, paginated processing diagnostics |
| `/dashboard/quarantine/[recordId]` | Escaped diagnostics and provenance |
| `/dashboard/sources` | Configured sources and factual synchronization state |
| `/dashboard/sources/[sourceId]` | Source inspection and guarded manual sync |

See [phase-3-completion.md](phase-3-completion.md) for the actual verification
verdict, evidence, limits, and prioritized debt.

## Task 34: frontend foundation

The foundation lives in `frontend/`, alongside the unchanged FastAPI backend.
It uses Next.js App Router, TypeScript, Tailwind, pnpm, and a small shadcn/ui base.

Delivered routes:

| Route | Purpose |
| --- | --- |
| `/` | Redirect to the internal dashboard |
| `/dashboard` | Overview with actual backend health and database readiness |
| `/dashboard/jobs` | Jobs placeholder |
| `/dashboard/sources` | Sources placeholder |
| `/dashboard/runs` | Pipeline Runs placeholder |
| `/dashboard/quarantine` | Quarantine placeholder |

The persistent shell contains a sidebar, header, active navigation, and mobile
navigation drawer. Loading, error, and not-found states provide the UI foundation.
Future detail pages can use App Router segments such as `jobs/[jobId]`,
`sources/[sourceId]`, and `runs/[runId]`; these are not implemented in Task 34.

## Data and component boundaries

```text
Browser → Next.js server components → centralized typed API client
        → FastAPI → PostgreSQL
```

The server reads `OPENROLE_API_BASE_URL`, configured locally in
`frontend/.env.local` from the committed `.env.example`. It is not a public
browser environment variable. Native fetch calls have a bounded timeout and
uncached status requests. Runtime validation checks the two consumed payloads.
Client components handle active navigation, the mobile drawer, and error retry.
No Next.js API routes or direct database access are introduced.

`GET /health` checks API process health. `GET /ready` checks PostgreSQL via the
existing backend probe. HTTP 503 with the documented readiness body means the
backend reports database unavailability. Transport or invalid-response failures
mean a check is unavailable; they do not establish the database's actual state.
Failures leave the shell and navigation visible. Reload to perform new checks.

[ADR 0002](adrs/0002-internal-dashboard-api-boundary.md) explains the decision.
[The frontend guide](../frontend/README.md) provides setup and validation commands.

## Acceptance and verification

Task 34 requires install, lint, TypeScript, focused API tests, and production
build checks, followed by desktop/mobile browser verification with FastAPI
running and with FastAPI stopped. Backend health/readiness regression tests
verify the existing contract. No migration is required.

No jobs table, history UI, lifecycle timeline, charts, run table, quarantine
workflow, source management, sync button, authentication, or public job search
is included. No dashboard metric is invented.

## Task 35: operational overview

`/dashboard` now composes three sections from existing FastAPI endpoints:

- System Status: independent API health and PostgreSQL readiness checks.
- Source Health: provider, active state, attempted/successful sync timestamps,
  latest run status, and actual run metrics for the configured monitoring source.
- Recent Pipeline Runs: the five latest attempts across all sources, including
  safe failure details and a distinct completed-with-errors/quarantine state.

There is no source-list API. For development, an optional server-only
`OPENROLE_DEFAULT_SOURCE_ID` identifies one source UUID. A missing ID means no
source is configured for dashboard monitoring, not that the database contains no
sources. An unknown/unavailable source has a separate failure state. Source IDs
are not hard-coded or inferred from the run list. The run list remains global.

All operational reads use `cache: no-store` and the existing bounded timeout.
Server-side reads settle concurrently and independently. Empty collections,
never-synced sources, and section failures remain visible within the shell.
Timestamps use deterministic UTC formatting and a stable server-rendered relative
value captured on page load. Duration is presentation arithmetic; backend statuses
and counters are displayed without recomputing domain decisions. Reload to refresh;
no polling is introduced.

The backend provides no aggregate job counts, so observed/not-observed/reappeared
totals are omitted. No charts, Jobs explorer, detail pages, sync controls, source
editing, authentication, new providers, backend endpoints, or migrations are added.

Verification includes pure formatting/status tests, API contract/error tests,
partial-failure composition tests, lint, TypeScript, production build, and real
FastAPI/PostgreSQL browser scenarios for empty, failed, partial-success, and outage
states. Temporary browser fixture data lives in an isolated migrated database.

## Task 36: Jobs explorer

`/dashboard/jobs` now lists logical Jobs and only their current canonical
JobVersions. Columns show title/external ID, company/provider, location,
workplace/employment type, lifecycle status, last seen, and current version.
First-seen and dated absence/reappearance facts remain available without changing
backend status vocabulary. Unknown canonical types display a dash; location is
never used to infer workplace type.

The new read-only administrative endpoint is `GET /api/v1/jobs`:

| Parameter | Contract |
| --- | --- |
| `limit` | Default 25, range 1–100 |
| `offset` | Default 0, range 0–2,147,483,647 |
| `lifecycle_status` | Optional `observed` or `not_observed` |
| `source_connection_id` | Optional UUID; unknown valid IDs return no matches |
| `q` | Optional maximum 200 characters, trimmed; literal case-insensitive containment in current title, current location text, or external job ID |

Response: `items`, filtered `total`, `limit`, `offset`. Each item contains identity
and lifecycle/freshness facts, `company: {id, name}`, `source: {id, provider}`, and
`current_version: {id, version_number, title, location_text, workplace_type,
employment_type}`. Canonical descriptions and source configuration are omitted.
Ordering is last seen descending, then job ID ascending. A missing current
version in the selected lifecycle/source scope yields HTTP 500
`CURRENT_JOB_VERSION_MISSING`, including when it lies outside the page or cannot
match a canonical search. Existing indexes/constraints suffice; no migration.

Frontend query state is `page`, `status`, `source`, and `q`; page size is 25 and
offset is `(page - 1) * 25`. Invalid presentation parameters safely default;
backend validation remains authoritative. Apply/Enter commits filters and resets
to page 1; pager links preserve filters. Back/forward and reload restore committed
state. Source filtering accepts a validated URL UUID; a source dropdown is omitted
until source discovery exists. `OPENROLE_DEFAULT_SOURCE_ID` affects only overview
monitoring, not the Jobs list.

Empty, filtered-empty, and out-of-range pages are distinct from failed requests.
A jobs-shaped loading skeleton and safe inline error retain the dashboard shell.
The semantic table scrolls inside a labeled region on smaller screens. Row titles
link to a UUID-validated placeholder at `/dashboard/jobs/{jobId}`; full details,
version/change/lifecycle histories, and provenance UI belong to Task 37.

Verification passed: 24 new PostgreSQL API cases, full backend suite (650 passed,
2 optional live-service tests skipped), Ruff/format/mypy, and frontend lint,
TypeScript, production build, and 58 tests including 16 new cases. Real browser
checks used 31 jobs in an isolated migrated PostgreSQL database: 25+6 pagination,
combined search/lifecycle/source filters, URL navigation/reload, distinct empty
states, placeholder links, loading, outage/recovery, and table scrolling without
document overflow at 320/390/768 px. Independent design/accessibility evaluation
passed; tablet filters now stack until the wider layout. Temporary fixture data
was removed after verification. Stop after Task 36.


## Task 39: Quarantine explorer and record detail

Task 39 implements `/dashboard/quarantine` and
`/dashboard/quarantine/[recordId]`. The list shows persisted diagnostics, source
company/provider, identity, run lineage, status, and timestamps. Detail adds
structured error details and the RawSnapshot/SourceConnection references.
`open` and `resolved` are the existing database statuses; both are inspection
states here. There are no resolve, retry, or replay controls.

The task explicitly authorizes the missing read-only backend endpoints:

- `GET /api/v1/quarantine`: `{items, total, limit, offset}`, default limit 25,
  maximum 100, nonnegative offset up to 2147483647.
- Optional filters: `status`, `pipeline_run_id`, `source_connection_id`, and
  exact `error_category` (trimmed, maximum 100 characters). Blank category means
  unfiltered; unknown valid scopes return an empty list.
- Ordering: `created_at DESC, id DESC`. The filtered count uses the same predicates
  as the bounded joined page. Error-details JSON is omitted from list rows.
- `GET /api/v1/quarantine/{record_id}`: one persisted record plus JSON diagnostic
  details; an unknown UUID returns `QUARANTINE_RECORD_NOT_FOUND` with HTTP 404.
- Invalid UUIDs, statuses, and pagination/category bounds return HTTP 422.

The UI stores `page`, `status`, `source`, `run`, and `category` in the URL. Status
and category controls apply server-side filters and reset to page one. Source/run
scopes arrive through validated UUID URLs, since discovery endpoints are absent.
Known category options follow the five production error categories; an unknown
active category remains inspectable. Pagination preserves the committed filters.
Empty, filtered-empty, out-of-range page, unavailable, loading, and detail-not-found
states remain distinct within the dashboard shell.

A malformed record can retain a recoverable external job ID. Such an identity can
contribute presence evidence subject to backend run-level checks; a missing ID can
prevent safe absence reconciliation. These pages explain that distinction without
computing run safety or changing job lifecycle state. Messages, locators, and
pretty JSON remain escaped text, including nested null/false/zero values. Long
content wraps or scrolls inside bounded, keyboard-focusable regions.

Source configuration/credentials, Bronze payloads, object keys, and signed storage
URLs are excluded. The RawSnapshot ID preserves the diagnostic lineage. No model,
migration, ingestion, or lifecycle rule changes are needed.

At this delivery stage Tasks 37 and 38 were deferred. The user
approved a minimal `/dashboard/runs/[runId]` placeholder for working navigation;
it displays only the validated UUID and links back to that run's filtered
quarantine records. It makes no run-detail request or completeness claim. The
Overview source-health card links a positive latest-run quarantine count to the
same filtered explorer. Full run metrics/detail integration remains Task 38.

Verification includes PostgreSQL API tests for filters, totals/order/pagination,
nullable identity, resolved records, JSON preservation, safe fields, read-only
behavior, and constant query counts; frontend tests cover URL state, API contracts,
escaped rendering, identity notes, and overview links. Browser verification uses
an isolated migrated PostgreSQL database and fixture-backed FastAPI, leaving the
normal development data unchanged. The full backend suite passed with 670 tests
and two optional live-service tests skipped; Ruff, format, and strict mypy passed.
Frontend lint, TypeScript, 77 tests, and the production build passed. Browser
checks verified known/unknown identity, schema diagnostics, resolved timestamps,
run/source/category filters, URL history, pagination, loading, empty/404/outage
states, escaped JSON, and keyboard scrolling at mobile/tablet widths. The two
detail accessibility findings were corrected with named landmark/region semantics;
fresh desktop/mobile audits reported zero violations or incomplete checks.
Stop after Task 39; Sources Explorer and Source Detail belong to Task 40.


## Task 40: Sources explorer and source detail

`/dashboard/sources` discovers real configured SourceConnections, showing safe
company identity, provider, active/inactive state, last attempted/successful sync,
and the latest run with fetched/quarantined counts. The list uses 25 rows per
page with URL `active=true|false` and `page` state. Applying a filter resets page
one; pagination/history/refresh retain it. Ordering is company name ascending,
then source UUID ascending. Empty, filtered-empty, out-of-range, unavailable,
and loading states are distinct.

The new `GET /api/v1/sources` accepts `limit` (default 25, 1–100), `offset`
(default 0, 0–2147483647), optional `is_active`, and optional `provider`
(`greenhouse`). It returns `{items, total, limit, offset}` with a filtered total.
The existing source-detail GET gains `company: {id, name, domain, careers_url}`;
all previous freshness/source/latest-run fields remain. Unknown UUIDs keep the
existing `SOURCE_CONNECTION_NOT_FOUND` HTTP 404 contract. Invalid filter/bound/UUID
values return HTTP 422. Neither list nor detail includes `configuration` or
`external_account_key`; this preserves the existing administrative read boundary.
No model or schema migration is required.

Source list/detail share an explicit joined projection. A correlated latest-run
ID selects `started_at DESC, id DESC` inside SQL, avoiding separate application
queries per source. The company inner join is supported by the required FK;
the run outer join preserves never-synchronized sources. List requests use two
SELECTs (count/page), detail one. Count/page reads share the existing isolation
level and may reflect concurrent ingestion between reads/page visits.

`/dashboard/sources/[sourceId]` displays source summary, freshness, latest-run
metrics, at most five recent source-specific runs, at most five quarantine
records, and source/company provenance IDs. Primary-source failures show a safe
unavailable/not-found state. Recent run/quarantine requests settle independently,
so one unavailable section preserves source facts and the other section. The
pipeline-run list now accepts `source_connection_id` before limit/offset; its
existing response and default limit 50 remain unchanged. Quarantine reuses its
existing source filter and a bounded five-record read.

Active/inactive is configuration, distinct from Completed/Failed run status. An
active source can show a newer failed attempt and an older successful sync. Null
sync times and no runs mean never synchronized, without an automatic failure
claim. No staleness threshold, health score, provider options, or decorative job
count is added. Company careers links accept only valid HTTP(S); unsafe protocols
are not linked. Debug/company text renders as escaped text.

Source Detail links to filtered Jobs and Quarantine explorers. The user approved
`/dashboard/runs?source=<UUID>` as a source-aware placeholder with a source-detail
return link while Task 38 was pending at this delivery stage; Task 42 completes it. Individual run links may carry a
validated source navigation context for the same return workflow, without
claiming full run inspection or making a run-detail request. Existing overview,
Jobs, and Quarantine surfaces receive narrow reverse source links. The overview
still uses its optional explicitly configured monitoring-source UUID; Task 40
does not add discovery selectors to other explorers.

Source administration remains read-only in Phase 3 at this point. No create,
edit, enable/disable, delete, manual sync, scheduling, or credentials controls
are present. Stop after Task 40; do not implement Task 41 actions.

Task 40 verification: 18 added PostgreSQL API cases passed; the API suite passed
107 tests and the full backend suite passed 688, with two optional live-service
tests skipped. Ruff, format, and strict mypy passed. Frontend lint, TypeScript,
97 tests (20 added), and the production build passed. Isolated PostgreSQL browser
fixtures verified active/completed, active/failed with older success, inactive,
never-synchronized, and quarantined sources; pagination/filter history; source
navigation; loading, empty, not-found, and outage states; independent related-API
failures; safe URLs and escaped text; and JSON/HTML sensitive-field exclusion.
Desktop/tablet/mobile checks passed down to 320px, including keyboard table
scrolling. Independent design review passed, with zero accessibility violations
or incomplete checks on desktop/mobile list and detail pages. Temporary fixture
data was isolated from the normal development database and removed after checks.

## Task 41: Manual source synchronization

Source Detail now supports one write action, Sync now, for an active source.
The source page remains server-rendered; its client control receives only the
source UUID, active state, and a Server Action reference. Inactive sources show
a disabled action with an explanation. Source creation, editing, deletion,
enabling/disabling, and scheduling remain outside this task.

The Server Action forwards one POST to the existing
`/api/v1/sources/{source_id}/sync` through the private API client. FastAPI and
SourceSyncService retain all synchronization and PostgreSQL locking behavior.
The request waits for complete synchronization; no asynchronous job acceptance,
polling, frontend retry, worker, queue, or progress percentage is implied.
Inspection requests retain their four-second timeout; mutation requests use a
separate five-minute timeout. A client timeout can leave backend work running,
so feedback reports uncertainty and recommends refreshing before retrying.

The button displays Synchronizing while the request is pending. A synchronous
local guard blocks duplicate clicks before React commits its disabled state;
the backend advisory lock protects against competing requests from other
clients. Completed feedback uses actual result counts. Completed-with-errors
uses warning feedback and the actual quarantine count, with run-scoped
quarantine navigation. Run links use returned UUIDs and the existing approved
source-aware placeholder; Task 38 was pending at this delivery stage; Task 42 completes it.

Known error codes map to trusted, specific messages, including lock conflict,
inactive/missing source, upstream timeout/failure, storage, database, and internal
failure. Arbitrary backend messages and exception strings remain hidden. The
current failed HTTP envelope has no PipelineRun UUID, so failure feedback does
not invent a run link. HTTP success is validated against the actual terminal
pipeline status and response identity rather than assumed to mean completion.

Terminal HTTP outcomes refresh authoritative source freshness, latest run,
recent runs, and quarantine activity, and invalidate related dashboard pages.
Network/configuration/transport-timeout errors preserve source facts and inline
feedback. No optimistic timestamp or metric updates occur. Existing uncached
reads fetch persisted state on refresh/navigation. Feedback need not survive a
full page reload because the underlying PipelineRun persists.

The backend URL and all credentials remain server-only. Next.js Server Action
origin protections are retained without broad CORS or allowed-origin changes.
The dashboard and administrative FastAPI endpoints remain unauthenticated at
application level: dashboard write actions must not be publicly exposed without
access control. Task 41 does not introduce authentication.

Stop after Task 41; do not implement Task 42 consolidation work.

Task 41 verification: frontend lint, TypeScript (including after build), the
production build, and all 111 Node tests passed; 14 mutation cases were added.
Existing backend API and ingestion regression suites passed 172 tests with one
existing TestClient deprecation warning. Backend code/schema/dependencies were
unchanged. Browser checks used an isolated migrated PostgreSQL database and the
actual SourceSyncService, advisory lock, storage, ingestion, and lifecycle code
with fixture Greenhouse transport. Initial sync created two jobs; identical sync
reported zero new/changed and two unchanged. Partial sync fetched two records,
accepted one, and quarantined one. Failed upstream timeout, competing-client
conflict without an extra run, disabled inactive action/backend enforcement,
disappearing-source 404, and fully stopped-backend feedback all passed. Two
immediate clicks produced one frontend request and one backend sync. Source,
latest run, recent runs/quarantine, Jobs, and overview reads reflected persisted
results. Forged-origin Server Actions were rejected before FastAPI forwarding;
rendered data excluded credentials/configuration and the private backend URL.
Independent UI review passed desktop/tablet/mobile down to 320px; completed,
partial, failed, and inactive accessibility checks reported zero violations or
incomplete checks. Live Greenhouse/R2 were not called. Temporary fixture data was
removed after verification; the normal development database was unchanged.

## Tasks 37–38 completed as Task 42 prerequisites

Job Detail preserves current content during independent history/source failures.
Versions, changes, and lifecycle events use their stored APIs; no browser diffing
or reconstructed lifecycle rules exist. Each section uses bounded lookahead
pagination because those APIs have no totals. Description HTML is sanitized on
the server; historical descriptions use the same policy. Exact decimal strings
are formatted without floating-point conversion. Safe HTTP(S) source links and
escaped structured metadata preserve the presentation boundary.

Runs use existing persisted metrics and ordering with one additive read-only
status filter. Source filtering predates this task. PostgreSQL applies both
predicates before pagination, with deterministic ID tie-breaking. The existing
response/default limit remain compatible. Explorer requests 26 records to show 25
and detect Next without inventing a total. RawSnapshot data and run lifecycle
counters are not exposed by this contract and remain absent from the UI.

## Task 42: integration and closure

Shared navigation section lookup keeps nested header/sidebar labels consistent.
Overview uses the common source-active badge, links runs to investigation pages,
and provides a focusable table scroll region. Quarantine run links retain known
source context. Source-health and quarantine-detail reads reject mismatched
resource identities. Unused placeholder code is removed after route replacement.
Existing UTC/status formatting remains shared; broad component extraction is
unnecessary. No frontend database access, domain rules, polling, new write action,
authentication, or provider is added.

Verification combines pure/API/rendered frontend tests, full PostgreSQL backend
regressions, a clean production build, and browser workflows against an isolated
migrated PostgreSQL database. Fixture HTTP uses the real ingestion services with
mocked source transport. The completion report distinguishes verified behavior
from limitations. Manual sync must remain externally access-controlled.
