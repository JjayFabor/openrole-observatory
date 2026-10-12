# Phase 4 completion report

## Summary and verdict

**Engineering verification: PASS — 2026-10-12.** Tasks 43–49 deliver the first
read-only public job-discovery prototype. All required automated checks and the
public journey passed. Developer understanding review remains pending; this
report does not claim the developer has answered the final questions.

This is prototype acceptance, not approval to expose the entire application on
the internet. The actual production origin is not configured, so indexing is
currently disabled. Dashboard/admin access must be externally protected before
deployment. JobPosting JSON-LD is deliberately **DEFERRED**. Phase 5 has not begun.

## Public architecture and routes

```text
Browser → Next.js public server components
        → server-only validated public API clients
        → FastAPI PublicJobQueryService / explicit public schemas
        → joined scalar PostgreSQL projections over persisted domain facts
```

FastAPI owns eligibility, search, pagination, lifecycle and change projection.
Next.js formats returned facts and sanitizes descriptions; it does not connect
to PostgreSQL, read Bronze objects, perform ingestion, infer employer intent or
recompute changes. Public routes are `/`, `/jobs` and `/jobs/{jobId}` with a
separate header/main/footer. `/robots.txt` and `/sitemap.xml` are runtime metadata
routes. Internal operational routes remain under `/dashboard/*`.

The landing is static and makes no backend reads. Discovery/detail are dynamic,
with deliberate `cache: no-store` reads and four-second timeouts at the current
small scale. This preserves observation visibility without introducing another
cache delay; it is not real-time source monitoring. React request memoization
shares detail between layout, metadata and page. Measured detail requests use one
primary read plus one independent changes read; discovery uses one public read.

## Requirement audit

| Task | Implemented | Tested | Documented | Understood |
| --- | --- | --- | --- | --- |
| 43: public API models | PASS | PostgreSQL contracts + ingestion-to-public acceptance | Delivered contracts and this report | Developer review pending |
| 44: public shell/landing | PASS | Render tests + browser CTA/keyboard/metadata | Frontend README and Phase 4 | Developer review pending |
| 45: discovery | PASS | Search/filter/order/bounds + five-page browser traversal | Query/caching/URL policy | Developer review pending |
| 46: detail | PASS | Lifecycle/sparse/404/source/HTML safety + real timeout/retry | Detail/sanitizer/URL contracts | Developer review pending |
| 47: change intelligence | PASS | Curated projection + pipeline-produced changes + independent failure | Public history and salary policy | Developer review pending |
| 48: SEO | PASS | Actual HTML/robots/sitemap + both build/configuration modes | Indexing and factual field matrix | Developer review pending |
| 49: integration/closure | PASS | Fresh full suites + end-to-end security/accessibility audit | This completion report | Developer review pending |

Before editing, the audit found the product behavior implemented and functional.
Missing pieces were a durable pipeline-to-public-contract acceptance story and
closure documentation. No reproducible broken public link, operational-data
leak, accessibility defect or responsive overflow was found. No unused library
or dead public placeholder warranted removal. The root README's “verified job
data” claim was changed to “source-backed listing data”; discovery metadata now
uses the plain phrase “last-observed timestamps.” No architecture redesign,
schema migration, new feature or dependency change was needed.

## Public APIs and discovery

| Public GET endpoint | Contract |
| --- | --- |
| `/api/v1/public/jobs` | Filtered summaries; total, limit and offset; no descriptions |
| `/api/v1/public/jobs/{jobId}` | Current listing, public company/provider facts, description and observation/lifecycle timestamps |
| `/api/v1/public/jobs/{jobId}/changes` | Bounded complete groups of curated material changes; default 10, maximum 50 |
| `/api/v1/public/jobs/sitemap` | Eligible public IDs only; UUID cursor; default/maximum batch 1000 |

These are separate schemas and projections from `/api/v1/jobs` and the other
internal endpoints. Public reads contain no pipeline/run/snapshot/observation or
source-connection IDs, external source identifiers, version/event IDs, content
hashes, canonical metadata, source configuration or quarantine diagnostics.
Public job UUIDs remain intentional routing identities in API JSON and links;
cards do not display UUID labels. Source descriptions remain untrusted public
content in the detail JSON; the frontend sanitizes them before HTML rendering.

Discovery requires an observed job, active source and exactly one current
version. Missing/duplicate current versions fail visibly with generic errors.
`q` is trimmed, case-insensitive literal containment across title, company or
location text; `location` searches location text, not inferred geography.
`%`/`_` are escaped as literals and SQL uses bound parameters. Text is bounded
at 200 characters. Workplace values are remote/hybrid/onsite. Employment values
are full_time/part_time/contract/temporary/internship/volunteer/other. Filters
intersect before counting and paging. List limit is 1–100, default 25; the UI
uses 25. Ordering is last_seen_at descending, then UUID ascending.

Native GET forms persist query state in URLs. Filter submission resets the page;
pagination retains filters. Reload, copied URLs and Back/Forward preserve the
committed controls/results. Invalid queries normalize; excessive pages clamp to
the actual last page. Offset pages can shift under concurrent ingestion and do
not promise a frozen snapshot. Fixed-count joined queries avoid per-job reads.

## Detail, observation semantics and source evidence

- **Observed:** OpenRole observed source presence; tentative absence does not
  immediately change this state. It is not an actively-hiring guarantee.
- **Not currently observed:** conservative absence confirmation from two safe
  source checks, not an employer closure/expiry declaration.
- **First observed:** earliest accepted OpenRole observation for this identity,
  not employer publication time.
- **Last observed:** latest accepted observation timestamp, not website update
  time or a claim that an unmonitored source is fresh now.

Detail presents current title/company, known location/types/salary, first/last
observation, lifecycle context, sanitized description, provider and source link.
Absent fields omit naturally or use the established useful description/location
fallback. Partial salary retains exact amounts with unavailable-unit qualifiers;
discovery cards require sufficiently complete salary units. No salary parsing,
currency guessing or free-text workplace/geography inference occurs.

Historical known URLs stay accessible with factual not-observed language and
optional absence-confirmed time. Reappearance makes current state observed and
shows return context secondarily, without treating the retained historical
absence timestamp as current absence. Inactive-source detail remains addressable
even though that source no longer participates in discovery/sitemap promotion.

Direct source identifies evidence from a configured employer ATS response. It
does not independently verify employer intent, immediate availability or every
employer's coverage. Users follow the original listing to check the employer's
current page; OpenRole has no Apply/Save/recommendation action.

## Public change intelligence

Persisted JobChangeEvents establish changes. The public projection retains
title, canonical location facts, workplace and employment, one semantic salary
entry and a description marker. Internal version keys group transitions but do
not cross the response boundary. Salary joins select exact scalar context from
the owning immutable versions; four internal salary fields become one readable
change. Description history contains no before/after HTML or snippets. Metadata
and source-URL-only changes do not become public history.

Dates show when OpenRole observed a change, not the exact employer action time.
Known initial/excluded-only histories return an empty success state. History is
bounded and loads independently under Suspense; history failure preserves the
current listing/source action with a secondary public-safe message.

## Security and public/internal boundary

The shared server-side `sanitize-html` allowlist removes scripts, styles, event
attributes, images, active embeds/forms, provider IDs/classes/inline positioning,
and unsafe links. Source headings normalize to h3 under the Description h2.
Only sanitized content reaches the HTML injection point. Source title/company
and other text use framework escaping, including metadata. Real browser tests
confirmed no adversarial script execution or provider control of the shell.

Public URLs require absolute HTTP(S) without credentials at backend/frontend
boundaries. The CTA also checks defensively and uses noopener/noreferrer with a
visible new-tab explanation. Deliberately corrupted unsafe source data returned
a generic unavailable result without publishing the unsafe URL or CTA. Neither
description links nor source actions fetch remote content on the server.

Normal public pages call only public contracts. Reused pure formatting helpers
under dashboard/source directories do not introduce administrative API calls.
Browser resources contain no direct FastAPI requests. Public JSON/HTML inspection
and regression tests exclude operational fields and private fixture markers;
failures omit backend diagnostics, SQLSTATE, stack traces and admin error codes.

Twenty-one browser JavaScript chunks were checked for private environment names,
the configured database URI, available R2 credentials, private fixture markers,
admin API calls and the server sanitizer dependency. Final configured builds also
used deliberate fake secret markers; none appeared in client chunks. No real
secret value was printed or written into QA reports. This is a targeted audit,
not proof of a publicly deployed access-control configuration.

## SEO and build safety

`OPENROLE_SITE_URL` supplies the explicit origin at build and startup. Public
canonical/OG URLs never derive from request Host or an invented production
fallback. Home/default Jobs are index/follow; meaningful filtered/paginated Jobs
are noindex/follow and canonical to `/jobs`. Meaningful observed detail is
self-canonical and index/follow; historical detail is HTTP 200, self-canonical,
noindex/follow. Reappearance restores observed policy at the same UUID URL.
Unavailable detail omits job canonical/OG URL; unknown detail is genuine HTTP 404.

Robots allows the public surface and excludes dashboard/API paths. Dashboard
layout independently inherits noindex/nofollow. Robots is not access control;
blocked crawlers may not read noindex, so operational access protection remains
required. APIs, dashboard and individual change groups are never sitemap pages.

Dynamic sitemap generation traverses all eligible UUID batches through the tiny
public endpoint. It omits not-observed/inactive jobs and invented lastModified
values. A failed walk returns a generic HTTP 500 without partial XML; more than
50,000 URLs fails explicitly instead of truncating. Batches see committed state
individually; concurrent membership changes are rechecked on later generation.
Missing/invalid origin yields noindex public metadata, no absolute canonical/OG
URL, robots Disallow `/`, and empty sitemap without an API request.

**JobPosting JSON-LD DEFERRED.** Required reliable employer datePosted is absent;
the Greenhouse mapper does not populate source_published_at. first_seen_at is not
publication and last-seen/absence dates do not establish validThrough. No
half-complete JSON-LD, inferred expiry, employer identifier, remote eligibility
or structured salary is emitted. See the
[Task 48 factual matrix](phase-4.md#jobposting-decision-and-factual-field-matrix).

Home is static; jobs/detail/robots/sitemap execute at runtime. Both configured
and unconfigured clean production builds passed with FastAPI unreachable. A
runtime API outage is handled deliberately; compilation does not require it.

## Fresh verification results

| Command | Result |
| --- | --- |
| Root `docker compose up -d postgres` | Existing normal PostgreSQL healthy; no volume deletion |
| Backend `uv run alembic upgrade head` | PASS; existing head retained; isolated QA database also migrated from empty |
| `uv run pytest tests/integration/api/test_phase_four_acceptance.py` | 2 passed |
| `uv run pytest tests/integration/api -k public` | 75 passed, 110 deselected |
| `uv run pytest` | 782 passed, 2 gated optional live Greenhouse/R2 tests skipped |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS; 182 files |
| `uv run mypy` | PASS; 175 source files |
| Frontend `pnpm lint` | PASS; no warnings |
| `pnpm tsc --noEmit` | PASS |
| `pnpm test` | 220 passed |
| `pnpm build`, configured/unconfigured | PASS with unreachable backend; isolated clean outputs |
| Workspace `pnpm build`, unconfigured | PASS with unreachable backend; final normal frontend rebuilt from current source |

The new durable acceptance tests use actual SourceSyncService, PostgreSQL,
filesystem Bronze storage, mocked Greenhouse HTTP and the existing controlled
canonical mapper. They connect unchanged/change ingestion to public discovery,
detail and history, first/confirmed absence, sitemap removal and reappearance.
A 120-job story verifies five-page traversal, source-failure preservation and
inactive-source exclusion while retaining detail. Normal tests call no live ATS/R2.
The existing TestClient/httpx deprecation warning is recorded, not hidden.

### End-to-end checklist evidence

| Checklist items | Verified result |
| --- | --- |
| Landing / Browse Jobs CTA / public shell | Factual copy, real navigation, no fake statistics/social proof/admin links |
| Default results / title/company/location search / all type filters / combinations | Actual browser IDs and totals agree with PostgreSQL/FastAPI across 21 cases |
| Pagination / URL sharing / reload / Back/Forward / page reset | 119 eligible jobs across five pages; no duplicates or skips; controls match URL |
| Invalid/long text queries / no-results / empty dataset | Normalization, 200-character bound, page clamp; empty actual normal database yields friendly copy and two configured static sitemap URLs |
| Observed / sparse / historical / reappeared detail | Current facts, safe fallbacks, observation timestamps and non-contradictory lifecycle context |
| Source link / unsafe URL / malicious description / layout abuse / escaping | Controlled employer destination opens; corruption fails safely; scripts/events/styles/unsafe hrefs removed; special title/company characters stay text |
| Recent changes / salary grouping / description marker / no changes | Pipeline-produced material changes, one salary entry, no old/new description HTML, clean initial history |
| Changes failure / primary failure / actual API transport timeout / retry | Current detail survives secondary failure; primary states retain public shell and filters; retry recovers after pausing/resuming only isolated FastAPI |
| Genuine job 404 / public error safety | Invalid and unknown UUIDs return public not-found; no stack trace/operator terminology |
| Landing/Jobs/filtered/detail metadata / historical noindex | Actual production HTML reflects lifecycle/query canonicals, robots and factual OG fields |
| robots / sitemap / return membership / dashboard noindex | 121 exact URLs: two static plus all 119 eligible jobs; historical/inactive/admin/API excluded; absence/return covered by real pipeline acceptance |
| Public API network / internal fields / browser secrets | Server-only public reads; public JSON/HTML/bundles exclude audited operational values and credentials |
| Desktop / tablet / mobile | Landing, long discovery/detail and changes at 1440/768/390/320px; no horizontal overflow; representative screenshots inspected |
| Keyboard / focus / semantics / forms / status accessibility | Header/CTA/search/selects/submit/pagination/result/Back/source navigation works; visible focus, labels, one final H1/main, textual status and readable errors |
| Accessibility / console | 27 recorded axe audits: zero violations and incomplete checks; normal browser console/page errors empty |
| Performance / payload / query sanity | Static landing: zero reads; detail: one shared primary + one history read; discovery: one bounded read; descriptions omitted from list; joined queries/history bounds retain existing tests |

Populated QA used a separate Alembic-migrated database: 120 main jobs through
actual repeated/change/absence/return synchronization, with 119 currently
discoverable, plus two inactive adversarial rows. Workplace/employment/salary
values were supplied only by the established test mapper; production Greenhouse
mapping remains conservative. Unsafe stored source URL was an explicitly
corrupted isolated test row, not a production persistence path. External source
navigation used a controlled destination; live employer availability was not
claimed. No fixture rows entered the developer database.

Browser harness issues were corrected before final verification: Enter must
submit from an input rather than a focused select; streaming assertions must
wait for final content; not-found heading assertions include its punctuation.
These required no product fixes. No failing required check remains. No independent
design review or broad security penetration test is claimed.

Evidence (commands, scripts, logs, JSON, screenshots) is retained under
`/tmp/openrole-task49-ke7cm04x`. Temporary QA services, database and copied
dependencies were removed; PostgreSQL confirmed the isolated database is absent.
Normal frontend/API services remain available. Final health/readiness, Home,
Jobs, dashboard Jobs, public discovery, robots and sitemap checks passed; the
normal public dataset remains empty and unchanged. The normal frontend was
rebuilt from final source and serves the corrected metadata wording with safe
unconfigured indexing behavior.

## Cleanup and documentation

No dead code or unused dependency was removed because the audit found none that
warranted deletion. Existing URL validators intentionally protect separate
boundaries. Runtime cleanup is one plain-language metadata adjustment; the
backend runtime, migrations and persistence rules are unchanged. README,
frontend README, product specification, architecture and Phase 4 status are
reconciled, and this report is new. Historical Phase 1–3 completion reports remain
historical records rather than being rewritten to describe later phases.

## Known limitations and technical debt

| Priority | Concrete limitation / follow-up |
| --- | --- |
| HIGH before public deployment | Enforce external access control or separately design admin authentication for `/dashboard`, administrative API routes, sync writes and internal OpenAPI docs. Robots/noindex provides no authorization. |
| HIGH before claiming exhaustive history | Existing unique `(job_id, content_hash)` can quarantine A→B→A content reversion. Review version identity/recurrence policy in a separate documented schema task; this public history shows accepted persisted changes only. |
| MEDIUM before indexing deployment | Configure actual HTTPS `OPENROLE_SITE_URL` consistently at build/startup and rebuild/restart. Current deployment remains unconfigured and noindex. |
| MEDIUM | Greenhouse-only configured coverage; manual sync and no monitoring SLA. Production mapping leaves unsupported salary/type/geography/sponsorship fields null. |
| MEDIUM as traffic grows | Measure literal containment scans, offset pages, invariant reads and uncached requests; introduce rate limits/cache/indexes only from actual demand. No frozen multi-page snapshot is promised. |
| MEDIUM as catalogue grows | Runtime sitemap walks every batch and has a 50,000-URL bound; design multiple sitemap files before exceeding it. |
| MEDIUM | Existing raw-object orphan/partial-progress recovery and stranded runs remain operational debt; no scheduler/replay/repair workflow is delivered. |
| LOW | Track the upstream TestClient/httpx warning; keep manual API types/projections synchronized with contracts. |

Recent public history is intentionally limited to ten transition groups, and
full public version/lifecycle/raw history is not a feature. JobPosting rich results
remain unavailable until reliable employer facts exist. Accounts, saved jobs,
alerts, additional providers, deduplication, enrichment and applications are not
implemented. These are real scope limits, not failed Phase 4 requirements.

## Phase 5 recommendation and readiness

The prototype has a verified foundation for another narrowly scoped capability
after developer review. First review the access-control and content-recurrence
risks; deployment and broader history guarantees depend on those decisions.

Recommend evaluating a second ATS provider next, beginning with a provider
abstraction audit. Coverage is currently the clearest product limitation and
Greenhouse-only assumptions remain in orchestration/public validation. Adding
one provider would exercise canonical boundaries and provide real evidence for
later cross-source entity resolution. Sponsorship/international evidence needs
explicit source facts; accounts/alerts add identity and operational obligations;
cross-source resolution should be grounded in actual multiple-source data.
This is a recommendation, not a rewrite of the existing Phase 5 roadmap or
authorization to start any of those features. No Phase 5 implementation is included.
