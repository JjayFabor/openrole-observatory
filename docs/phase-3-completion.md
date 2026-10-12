# Phase 3 completion report

## Summary

Verification verdict: **PASS** (2026-10-09).

Phase 3 delivers an internal operational dashboard over the existing Greenhouse
pipeline. Task 42 explicitly includes the previously deferred Tasks 37–38, followed
by integration polish and closure verification. This report records final automated and browser
verification. Developer understanding review remains
pending; no Phase 4 code is included.

## Frontend architecture

```text
Browser → Next.js server components / guarded Server Action
        → typed server-only API client → FastAPI
        → PostgreSQL queries / existing pipeline services
```

FastAPI owns ingestion, transactions, validation, changes, lifecycle decisions,
locking, and persistence. The frontend validates consumed API contracts and
formats their facts. It never connects to PostgreSQL, reads object storage, or
recalculates change/lifecycle events. API configuration remains server-only.
Most pages are server components; client boundaries serve navigation, existing
filter drafts, error retry, and manual synchronization. Reads are uncached and
bounded. The synchronous write has its separate five-minute timeout.

## Routes delivered

| Route | Read surface |
| --- | --- |
| `/dashboard` | Independent API health, DB readiness, monitored source and five recent runs |
| `/dashboard/jobs` | Current listings, literal text/lifecycle/source filters and total-based pagination |
| `/dashboard/jobs/[jobId]` | Current listing, descriptions, changes, versions, lifecycle and provenance |
| `/dashboard/runs` | Status/source filters, newest-first stored metrics and bounded pagination |
| `/dashboard/runs/[runId]` | Stored run outcome, metrics, failure context and optional source information |
| `/dashboard/quarantine` | Status/category/source/run filters, diagnostics and total-based pagination |
| `/dashboard/quarantine/[recordId]` | One escaped diagnostic record with identity and provenance |
| `/dashboard/sources` | Company/provider, configured active state, timestamps and latest run |
| `/dashboard/sources/[sourceId]` | Source facts, independent recent activity, scoped navigation and manual sync |

## Read-only surfaces and semantics

Observed means OpenRole observed source evidence. Not observed means conservative
absence confirmation, not an employer closure declaration. First absence remains
a dated tentative fact under Observed. Reappearance retains historical evidence.
Content versions and persisted field changes describe canonical content;
lifecycle events describe presence decisions. Neither is reconstructed in the UI.

Run metrics distinguish fetched, valid and quarantined records from new, changed
and unchanged canonical jobs. Completed with errors means valid records processed
alongside quarantines; Failed means synchronization did not complete successfully.
A successful synchronization timestamp can advance with isolated record errors.
Source active configuration is independent of latest-run success/failure. Numeric
zero is a stored count; null completion timestamps remain unavailable.

The backend adds only an optional enum-validated run status filter, applied with
source filtering before pagination. Schema, migration, pipeline transactions and
domain behavior are unchanged. The existing run/history APIs have no total;
26-row lookahead displays 25 rows and enables Next without inventing counts.
Jobs, Sources and Quarantine retain their existing filtered totals. All pagination
uses URL state; changed filters reset page one.

## Write actions

Manual source synchronization is the only dashboard write. The Source Detail
button calls a Next.js Server Action and the existing FastAPI sync endpoint.
Local duplicate guards and pending/refresh disabling complement the backend
PostgreSQL lock. Inactive, missing, conflict, completed, partial and failed outcomes
use authoritative backend status/code pairs. Terminal HTTP outcomes invalidate
operational views and refresh persisted facts. Transport loss preserves existing
facts because the outcome may be unknown; refresh before retrying. No optimistic
success, polling, cancellation, replay, retry, CRUD or scheduler is added.

## Verification results

### Pre-implementation audit

| Audit area | Finding / decision |
| --- | --- |
| Component consistency | Keep established shell, spacing and typography; fill three missing investigation routes |
| Navigation | Fix nested header labels, overview investigation links and quarantine source context |
| Duplication | Reuse source-active badge; retain simple feature pagination/header markup rather than broad extraction |
| Terminology | Preserve observation facts and partial-success semantics, never imply employer intent |
| Badges/colors | Existing text/status badges shared; overview active badge was the inconsistent exception |
| Loading/errors | Existing real pages separate empty/error; new routes need real primary lookup and 404 handling |
| Security | Existing API boundary safe; new HTML sanitizer and resource-identity validation are required |
| Responsive | Verify long HTML, metadata, IDs and errors against desktop/tablet/mobile fixtures |
| Accessibility | Keep semantic tables and Radix drawer; make overview scroll region focusable |
| Cleanup | Remove unused placeholder component after route replacement; reconcile stale roadmap/current-scope docs |

### Automated checks

- `backend: uv run pytest tests/integration/api -q`: **110 passed**.
- `backend: uv run pytest`: **691 passed, 2 skipped**. Skips are optional live
  Greenhouse and R2 tests; normal tests use stored fixtures/mocked transport.
- `backend: uv run ruff check .`: **PASS**.
- `backend: uv run mypy`: **PASS**, 163 source files.
- `frontend: pnpm lint`: **PASS**.
- `frontend: pnpm typecheck` (`tsc --noEmit`): **PASS**.
- `frontend: pnpm test`: **142 passed**, 31 new cases.
- `frontend: pnpm build`: **PASS**, clean production build with all nine dynamic
  dashboard routes; no backend is required at build time.
- Existing upstream Starlette TestClient/httpx deprecation warning remains; no
  test failure is hidden.

### Browser and end-to-end evidence

Final production-build browser verification passed. Isolated fixtures used a newly
migrated PostgreSQL database, real acquisition/storage/ingestion/lifecycle/run
services, and mocked source HTTP. They include 56 primary jobs, 31 versions and
35 field changes for one job, reappearance, confirmed and tentative absences,
51 primary-source quarantines, completed/partial/failed runs and multi-page
source/run data. Salary/workplace enrichment is a fixture-only controlled mapper;
the production Greenhouse mapper remains conservative.

A separate real FastAPI instance configured with an unreachable PostgreSQL port
already verifies `/health` HTTP 200 while `/ready` HTTP 503 reports DB unavailable.
The running developer PostgreSQL instance is not stopped or modified for that
check. The empty normal database was rechecked after implementation. Unknown valid
UUIDs and invalid IDs show resource-specific Next.js not-found pages; backend
resource APIs retain actual HTTP 404 responses.

| Browser check | Verified result |
| --- | --- |
| All nine routes | Real data/empty/failure behavior and usable shell |
| Jobs → detail → history | Current version, exact salary, persisted changes, independent version/change pages, Back/Forward |
| Lifecycle story | Reappearance, confirmed not observed, and actual first absence under Observed |
| Source → Sync → Run | Actual completed outcome, unchanged idempotency metrics and persisted Run Detail |
| Partial → quarantine → detail → run | Actual completed-with-errors feedback, scoped record, real related run |
| Overview → source → run → quarantine/jobs | Source scopes and authoritative persisted links retained |
| Manual sync | Pending, double-click protection, completed, partial, failed, inactive, actual backend lock conflict and network failure |
| Refresh | Latest source/run/quarantine facts change after terminal results without a full browser reload |
| Pagination | First/middle/last pages match backend ordering; no duplicate/missing rows, correct disabled navigation |
| URL state | Combined filters reset page; refresh, copied URLs, Back/Forward, clear and malformed parameters work |
| Empty / 404 | Real empty database, filter misses, and missing/invalid Job, Run, Source and Quarantine IDs |
| Secondary failures | Actual history/source HTTP 503 preserves current listing and persisted run facts |
| Backend outage | Actual fixture FastAPI stopped; all nine pages fail safely; sync releases pending and preserves loaded facts |
| DB outage | Separate real FastAPI with unreachable PostgreSQL: API Healthy, database Not ready |
| Running run | Actual stored Running status and null completion; later refresh displays its completed outcome |
| Responsive | All nine routes at 1400/768/390/320; long-URL history also at 1440/768/390/375/320 |
| Keyboard | Filters, pagination/table links, sync, source-link focus, drawer navigation and Escape/focus return |
| Security | Malicious current/historical HTML removed; diagnostics escaped; long JSON retains zero/false/null; private configuration absent |
| API boundary | No browser-to-FastAPI resources; private API/database/R2 variables and fixture secret absent from static bundles |
| Origin protection | Forged-origin Server Action rejected before any FastAPI synchronization POST |
| Console / logs | No avoidable React/hydration/console exceptions; intentional 404, source failure and origin-rejection tests distinguished from normal reads |

Independent evaluation initially required revision: a long source URL expanded
mobile history grids. Explicit shrinking grid columns, constrained minimum widths,
and block wrapping fixed it. Fresh evaluations then passed, including the complete
1,439-character value. Final fresh accessibility audits reported zero violations
and zero incomplete checks. A final wording correction avoids claiming that a
tentative absence came from the latest successful sync: later partial runs can
advance success timestamps while skipping lifecycle reconciliation.

Browser automation initially clicked the union center between wrapped anchor
lines; a native pointer click inside the first text rectangle and keyboard Enter
verified actual navigation. This was a test-tool geometry limitation.

Evidence remains in `/tmp/openrole-task42-N1NlvvM6`: test/build logs, browser scripts
and logs, screenshots, contract checks, and independent evaluation artifacts.
Descriptions/URLs were pipeline-persisted; long adversarial run/quarantine text was
explicitly augmented only in isolated test rows. The test database and temporary
services were removed. Normal FastAPI on 8000 and Next.js on 3000 remain running;
health, readiness and dashboard were checked after cleanup. No developer rows,
credentials, or environment files were changed.

## Security notes

Descriptions cross a maintained server-side HTML allowlist sanitizer before
rendering, including historical descriptions. Scripts, styles, event attributes,
unsafe protocols and active embedded content are rejected. External links accept
absolute HTTP(S) URLs without embedded credentials. Structured diagnostics and
metadata render as escaped text. Source configuration/account keys and storage
credentials remain excluded from read contracts and browser output. The API
client normalizes caught errors; manual sync uses trusted messages rather than
arbitrary backend exception text. Server Action origin restrictions stay enabled.

The dashboard has no application authentication and includes a write action.
Keep it local or externally access-controlled; it must not be publicly exposed.

## Known limitations

- Greenhouse is the only supported provider. Production canonical enrichment
  does not infer workplace, salary or employment fields from free text.
- Overview monitors one optional server-configured source; recent runs are global.
- Offset pagination and independent reads do not represent a stable database
  snapshot under concurrent ingestion.
- Run/history totals, run lifecycle reconciliation counters, raw snapshot details,
  and efficiently linked touched jobs are absent from current read contracts.
- No polling: running outcomes refresh on navigation/manual reload. A synchronous
  write timeout cannot establish whether processing stopped.
- Existing historical content-hash uniqueness can quarantine an A→B→A canonical
  reversion rather than creating another identical historical version. This
  backend limitation predates the dashboard.
- Source creation/editing and quarantine resolution/replay remain deferred.
- Salary appears on current/historical detail; the Jobs explorer read contract
  does not contain salary fields, so no list salary is fabricated.

## Technical debt

| Priority | Concrete follow-up |
| --- | --- |
| HIGH | Preserve external access control and design a separate safe public/read-only boundary before public release |
| HIGH | Resolve canonical A→B→A history behavior before claiming complete change-history coverage |
| MEDIUM | Introduce job/run history totals or cursor pagination only when investigation volume justifies it |
| MEDIUM | Replace temporary single-source overview configuration with an explicit operator selection model |
| MEDIUM | Evaluate asynchronous sync only when synchronous duration and unknown outcomes become operational problems |
| LOW | Track upstream ESLint plugin and TestClient/httpx compatibility before dependency upgrades |
| LOW | Consider generated API contract types when manual contract maintenance becomes measurable overhead |

## Phase 4 readiness

Engineering verification is **PASS**; the internal dashboard is ready for the next
planning step, with developer understanding review and the access/history risks
still requiring attention before public release. Recommendation: review the existing [Verified Job Discovery proposal](phase-4.md)
after Phase 3 verification and developer understanding review. Begin with a
small public read model and trustworthy freshness/provenance language, keeping
administrative diagnostics and writes separate. Review access boundaries and
history limitations first. No Phase 4 implementation is included here.

## Changed files in Task 42 and its authorized prerequisites

Generated/ignored build caches and temporary verification artifacts are excluded.

| File | Change | Purpose |
| --- | --- | --- |
| `README.md` | Modified | Current dashboard status, local setup, run filter contract and reconciled proposed roadmap. |
| `backend/app/api/pipeline_runs.py` | Modified | Optional enum status filter and bounded PostgreSQL offset at HTTP boundary. |
| `backend/app/pipeline_runs/query_service.py` | Modified | Pass status predicate through the read service. |
| `backend/app/pipeline_runs/repository.py` | Modified | Apply status/source predicates before ordered SQL pagination. |
| `backend/tests/integration/api/test_admin_api.py` | Modified | Keep administrative API test stub compatible with the additive filter. |
| `backend/tests/integration/api/test_sources_api.py` | Modified | PostgreSQL status/source filtering, stable pagination and invalid-query regression tests. |
| `docs/architecture.md` | Modified | Actual investigation API boundaries and final Phase 3/next-phase direction. |
| `docs/phase-2.md` | Modified | Remove stale Phase 3 Lever/Ashby roadmap claim. |
| `docs/phase-3-completion.md` | Created | Completion verdict, architecture, verification, limitations, debt and review guide. |
| `docs/phase-3.md` | Modified | Final route scope, prerequisite completion and Task 42 integration decisions. |
| `docs/product-spec.md` | Modified | Delivered internal dashboard scope and administrative action/access boundaries. |
| `frontend/README.md` | Modified | All routes, filters, history pagination, sanitizer and manual-sync setup. |
| `frontend/app/dashboard/jobs/[jobId]/loading.tsx` | Created | Route-specific loading skeleton for real server reads. |
| `frontend/app/dashboard/jobs/[jobId]/not-found.tsx` | Created | Resource-specific missing/invalid identifier state and return link. |
| `frontend/app/dashboard/jobs/[jobId]/page.tsx` | Modified | Primary job resource route with real detail and safe unavailable state. |
| `frontend/app/dashboard/runs/[runId]/loading.tsx` | Created | Route-specific loading skeleton for real server reads. |
| `frontend/app/dashboard/runs/[runId]/not-found.tsx` | Created | Resource-specific missing/invalid identifier state and return link. |
| `frontend/app/dashboard/runs/[runId]/page.tsx` | Modified | Persisted run resource route with real detail and safe unavailable state. |
| `frontend/app/dashboard/runs/loading.tsx` | Created | Route-specific loading skeleton for real server reads. |
| `frontend/app/dashboard/runs/page.tsx` | Modified | Runs explorer route with actual filters, bounded pagination and empty/error states. |
| `frontend/components/dashboard/dashboard-header.tsx` | Modified | Correct section label on nested detail routes. |
| `frontend/components/dashboard/navigation.tsx` | Modified | Use the shared section lookup for active navigation. |
| `frontend/components/dashboard/placeholder-page.tsx` | Removed | Remove the unused placeholder implementation. |
| `frontend/components/dashboard/recent-runs.tsx` | Modified | Investigation links, accessible scroll region and long error wrapping. |
| `frontend/components/dashboard/source-health-card.tsx` | Modified | Reuse consistent configured-active status badge. |
| `frontend/components/jobs/job-description.tsx` | Created | Render only sanitized description HTML. |
| `frontend/components/jobs/job-detail.tsx` | Created | Current listing, factual lifecycle/source summary, metadata and provenance. |
| `frontend/components/jobs/job-history-pagination.tsx` | Created | Section pagination preserving independent query state. |
| `frontend/components/jobs/job-history.tsx` | Created | Version/change/lifecycle sections with bounded, wrapping persisted values. |
| `frontend/components/quarantine/quarantine-detail.tsx` | Modified | Preserve source context in record-to-run navigation. |
| `frontend/components/quarantine/quarantine-table.tsx` | Modified | Preserve source context in related-run links. |
| `frontend/components/runs/run-detail.tsx` | Created | Stored run metrics/status/timestamps/diagnostics and related navigation. |
| `frontend/components/runs/run-filters.tsx` | Created | Server-rendered native GET status/source filter form. |
| `frontend/components/runs/runs-pagination.tsx` | Created | Bounded Previous/Next without an invented total. |
| `frontend/components/runs/runs-table.tsx` | Created | Semantic run table with actual metrics and source/run links. |
| `frontend/lib/api/job-detail.ts` | Created | Primary job with independently settled history/source reads. |
| `frontend/lib/api/job-history.ts` | Created | Validated current job and bounded persisted history reads. |
| `frontend/lib/api/pipeline-runs.ts` | Modified | Compatible five-recent reads plus explorer/status/source and detail reads. |
| `frontend/lib/api/quarantine.ts` | Modified | Reject mismatched returned detail identity. |
| `frontend/lib/api/run-detail.ts` | Created | Primary persisted run with optional source summary. |
| `frontend/lib/api/sources.ts` | Modified | Validate monitoring source/latest-run identities and project safe health fields. |
| `frontend/lib/api/types.ts` | Modified | Exact job/history/run and composed inspection contracts. |
| `frontend/lib/dashboard/navigation.ts` | Created | Shared section lookup with correct nested-route matching. |
| `frontend/lib/jobs/description-html.ts` | Created | Server-only sanitize-html allowlist and safe link policy. |
| `frontend/lib/jobs/history-query.ts` | Created | Independent bounded history URL state. |
| `frontend/lib/jobs/presentation.ts` | Modified | Exact decimal salary, field/event labels and persisted change grouping. |
| `frontend/lib/runs/query-state.ts` | Created | Validated status/source/page URL serialization. |
| `frontend/package.json` | Modified | Established server-side sanitizer and its TypeScript declarations. |
| `frontend/pnpm-lock.yaml` | Modified | Lock the installed sanitizer/declaration dependency graph. |
| `frontend/tests/dashboard-navigation.test.ts` | Created | Nested route and prefix-collision matching. |
| `frontend/tests/investigation-render-fixture.tsx` | Created | Actual component fixtures with adversarial HTML, long URLs and tentative evidence. |
| `frontend/tests/investigation-safety.test.ts` | Created | Actual rendering safety, escaped recorded facts and cross-page links. |
| `frontend/tests/job-description.test.ts` | Created | Sanitizer attacks, allowed formatting and safe/unsafe link protocols. |
| `frontend/tests/job-detail-fixtures.ts` | Created | Typed current/history/source fixture contracts. |
| `frontend/tests/job-detail-presentation.test.ts` | Created | Exact salaries, unknown labels and grouping without re-diffing. |
| `frontend/tests/job-detail.test.ts` | Created | Primary job/not-found and independent secondary failures. |
| `frontend/tests/job-history-api.test.ts` | Created | History/current contracts, identity, decimals and bounded lookahead. |
| `frontend/tests/job-history-query.test.ts` | Created | Independent URL pagination and malformed page handling. |
| `frontend/tests/pipeline-runs.test.ts` | Modified | Compatible recent/explorer/detail contracts and filtered lookahead. |
| `frontend/tests/quarantine-api.test.ts` | Modified | Requested/returned quarantine identity hardening. |
| `frontend/tests/quarantine-safety.test.ts` | Modified | Escaped diagnostics and source-aware related-run links. |
| `frontend/tests/run-detail.test.ts` | Created | Primary run/not-found with independent source failure. |
| `frontend/tests/runs-query-state.test.ts` | Created | Actual run enums, source scope, bounds and shareable URLs. |
| `frontend/tests/sources.test.ts` | Modified | Monitoring source and latest-run identity consistency. |
