# OpenRole Observatory — Phase 4: Public Job Discovery Product

Task 43 delivers the backend public read boundary described in
[the final API contract](#task-43-delivered-public-api-contract). Task 44 adds the
[public shell and landing foundation](#task-44-public-shell-and-landing-foundation)
at `/`. Task 45 delivers public discovery at `/jobs`. Task 46 replaces its
minimal preview with current public listing detail, lifecycle/observation evidence,
safe source linking and sanitized description. Task 47 adds curated recent listing
changes from persisted events. Task 48 adds metadata, canonical/indexing policy,
robots and a runtime sitemap; JobPosting markup is deferred for missing facts.
Task 49 closes engineering verification with PASS; see
[the Phase 4 completion report](phase-4-completion.md) for final behavior,
commands, E2E evidence and limitations. Developer understanding review and
deployment configuration/protection remain outstanding. The recommendations
below describe the broader phase; task delivery sections preserve evidence as
of each task's completion rather than implying earlier placeholders still exist.

## 1. Purpose

Phases 1–3 built the operational foundation:

```text
Phase 1
Reliable Greenhouse ingestion

Phase 2
Job history, change intelligence, and lifecycle tracking

Phase 3
Internal operational dashboard
```

Phase 4 turns that infrastructure into the first real user-facing OpenRole product.

The core product question becomes:

> Can a job seeker discover listings that OpenRole has recently observed directly from employer ATS sources and understand how trustworthy/fresh that information is?

OpenRole should differentiate itself through:

- direct-source provenance;
- freshness;
- historical observation;
- listing changes;
- factual lifecycle status;
- transparent uncertainty.

It should **not** behave like another generic scraped job board.

---

# 2. Phase 4 Product Position

OpenRole is not trying to say:

```text
"This job is definitely hiring."
```

It can accurately say:

```text
"OpenRole observed this listing directly on the employer's ATS 18 minutes ago."
```

Or:

```text
"This listing was previously observed but has not appeared in the last two successful source checks."
```

Or:

```text
"This listing reappeared after previously becoming not observed."
```

That evidence should become visible to job seekers.

---

# 3. Phase 4 Objective

Build a public/read-only discovery experience:

```text
Public Home
    ↓
Job Discovery
    ↓
Search / Filters
    ↓
Job Detail
    ↓
Freshness + Source Evidence
    ↓
Historical Changes
```

The internal dashboard from Phase 3 remains separate.

Conceptually:

```text
/
├── public product
│
├── /jobs
│   └── /jobs/[jobId]
│
└── /dashboard
    └── internal operations
```

---

# 4. Primary User

Initial user:

> Software, data, engineering, or technology job seeker who wants listings backed by direct employer sources.

The first public product does not need to support every job category.

The initial dataset is already limited by configured Greenhouse sources.

That is acceptable.

---

# 5. Product Principles

## 5.1 Evidence before claims

Display:

```text
Observed directly at source
Last observed
Source provider
Employer careers source
```

Do not display unsupported labels such as:

```text
Verified hiring
Actively hiring
Guaranteed open
Real job
Not a ghost job
```

unless future evidence supports those claims.

---

## 5.2 Freshness is first-class

Freshness should be visible throughout the public product.

Example:

```text
Observed 22 minutes ago
```

or:

```text
Last observed October 8, 2026
```

A user should not need to hunt for this information.

---

## 5.3 Current status must be factual

Use:

```text
Observed
Not observed
```

not:

```text
Open
Closed
Expired
```

unless the provider explicitly supplies those states.

---

## 5.4 Source provenance is valuable

A listing should clearly link back to:

```text
Employer ATS source
```

where possible.

OpenRole should make it obvious that the listing was obtained from a direct source rather than scraped from another job board.

---

## 5.5 History should be useful, not overwhelming

Historical changes are a differentiator.

But the public UI should summarize them clearly.

Example:

```text
Changed 3 days ago

Workplace
Remote → Hybrid

Salary
Not listed → USD 90,000–110,000
```

Do not expose internal PipelineRun IDs and technical provenance by default on public pages.

---

# 6. In Scope

Phase 4 includes:

- public application shell;
- public landing/home page;
- public jobs discovery page;
- public job detail page;
- search;
- lifecycle filtering;
- location filtering where supported;
- workplace filtering;
- employment-type filtering;
- source freshness;
- source-backed evidence;
- change-history presentation;
- pagination;
- shareable URLs;
- SEO foundations;
- accessible metadata;
- public-safe API/read models if needed;
- public empty/error states;
- Phase 4 end-to-end verification.

---

# 7. Explicitly Out of Scope

Do NOT implement yet:

- user accounts;
- saved jobs;
- applications;
- resume uploads;
- email alerts;
- notifications;
- recommendations;
- matching;
- AI summaries;
- sponsorship inference;
- relocation inference;
- salary estimation;
- employer reviews;
- Lever;
- Ashby;
- cross-source deduplication;
- paid plans;
- subscriptions.

The first public product should remain focused.

---

# 8. Public vs Internal Separation

Keep:

```text
/dashboard/*
```

as the internal operational interface.

Create public routes separately.

Recommended:

```text
/
 /jobs
 /jobs/[jobId]
```

Do not reuse internal administrative pages directly.

Public pages should expose a smaller, safer read model.

---

# 9. Why Separate Read Models Matter

Internal Job Detail may expose:

```text
SourceConnection ID
SourceObservation ID
content hash
PipelineRun ID
RawSnapshot ID
```

Public users do not need these.

Public API/UI should expose:

```text
title
company
location
employment
workplace
salary
description
last observed
first observed
lifecycle status
source link
selected historical changes
```

This prevents internal architecture from leaking into the product contract.

---

# 10. Public Job Eligibility

Define clearly which Jobs may appear publicly.

Recommended default:

```text
lifecycle_status = observed
AND source_connection.is_active = true
```

Only currently observed listings appear in the default public results.
Task 43 also requires an active source and exactly one current canonical version.
Inactive-source detail remains addressable; no freshness expiry is invented.

Do not mix `not_observed` jobs into normal discovery results.

---

# 11. Not-Observed Listings

Historical public URLs for a Job may remain accessible.

Example:

```text
/jobs/{jobId}
```

for a now `not_observed` listing.

The page should show:

```text
Not currently observed
```

with last-seen information.

This preserves useful historical links without presenting it as a current opportunity.

---

# 12. Default Search Results

Recommended default public search:

```text
Observed Jobs only
ordered by last_seen_at DESC
```

This gives freshness-first behavior.

---

# 13. Search Endpoint

The internal administrative:

```text
GET /api/v1/jobs
```

may not be the ideal long-term public contract.

Consider a dedicated public endpoint:

```http
GET /api/v1/public/jobs
```

or:

```http
GET /api/public/jobs
```

depending on current API conventions.

Do not expose internal-only fields simply because an endpoint already exists.

---

# 14. Public Job List Read Model

Conceptually:

```json
{
  "items": [
    {
      "id": "...",
      "title": "Backend Engineer",

      "company": {
        "name": "Example Company",
        "domain": "example.com"
      },

      "location_text": "Remote",
      "workplace_type": "remote",
      "employment_type": "full_time",

      "salary_min": "90000.00",
      "salary_max": "110000.00",
      "salary_currency": "USD",
      "salary_period": "year",

      "first_seen_at": "...",
      "last_seen_at": "...",

      "source_provider": "greenhouse"
    }
  ],

  "total": 120,
  "limit": 25,
  "offset": 0
}
```

Do not expose:

```text
PipelineRun IDs
SourceObservation IDs
RawSnapshot IDs
internal error information
```

---

# 15. Public Search

Implement simple database-backed search.

Search initially:

```text
title
company name
location_text
```

Potentially:

```text
description
```

only if current query performance remains reasonable.

Do not add Elasticsearch.

Do not add vector search.

PostgreSQL is enough.

---

# 16. Search Semantics

Initial simple behavior:

```text
case-insensitive text containment
```

or PostgreSQL text search if already straightforward.

Do not call the feature:

```text
AI Search
Semantic Search
```

unless it actually becomes one later.

---

# 17. Filter Set

Recommended Phase 4 filters:

```text
Search
Location
Workplace type
Employment type
```

Potential:

```text
Company
```

if source/company coverage makes it useful.

Do not expose every database field as a filter.

---

# 18. Lifecycle Filter

Default:

```text
Observed
```

For public discovery, an optional filter may allow:

```text
Include not-observed listings
```

but this is not essential initially.

Recommended simpler behavior:

> public discovery lists observed Jobs only.

Historical not-observed Jobs remain accessible through their detail URLs.

---

# 19. Location Filter

Use canonical location fields only.

Possible:

```text
location_text
country_code
```

Do not infer missing geography in frontend.

If structured country data coverage is poor:

start with simple location text search.

---

# 20. Workplace Filter

Canonical values:

```text
Remote
Hybrid
On-site
Not stated
```

Only filter based on the backend canonical value.

Do not infer workplace type from descriptions.

---

# 21. Employment Filter

Canonical values may include:

```text
Full-time
Part-time
Contract
Internship
Temporary
```

Use backend-supported enum values only.

---

# 22. Salary

Display structured salary when available.

Do NOT make salary filtering a Phase 4 requirement unless data coverage proves sufficient.

Do not infer salary from job descriptions.

---

# 23. Sorting

Recommended initial sorting:

```text
Freshest
```

meaning:

```text
last_seen_at DESC
```

Potential later sort:

```text
Recently added
```

using:

```text
first_seen_at DESC
```

For Phase 4, one default sort may be enough.

---

# 24. Jobs Discovery Page

Route:

```text
/jobs
```

Recommended layout:

```text
OpenRole Jobs

Direct-source listings with visible freshness.

[ Search jobs                    ]
[ Location ] [ Workplace ] [ Employment ]

120 jobs

-----------------------------------------
Backend Engineer
Example Company
Remote · Full-time

Observed 22 min ago
Greenhouse source

-----------------------------------------
...
```

Keep it simple.

---

# 25. Job Cards vs Table

Public users should not receive the dense internal dashboard table.

Use a readable list/card structure.

Avoid oversized decorative cards.

One listing row/card might show:

```text
Title
Company
Location
Workplace / employment
Salary if available
Freshness
```

---

# 26. Freshness Indicator

Examples:

```text
Observed 18 min ago
Observed today
Last observed Oct 8
```

Be factual.

Avoid:

```text
Fresh
Hot
Trending
```

unless separately defined.

---

# 27. Source Indicator

Subtle indicator:

```text
Direct source · Greenhouse
```

or:

```text
Source: Greenhouse
```

Potential tooltip:

```text
OpenRole observed this listing directly from the employer's ATS.
```

This communicates the product difference.

---

# 28. Public Job Detail

Route:

```text
/jobs/[jobId]
```

Different from:

```text
/dashboard/jobs/[jobId]
```

The public page should emphasize the opportunity, not internal architecture.

---

# 29. Public Job Detail Structure

Recommended:

```text
Title
Company

Observed 18 minutes ago
Remote · Full-time

[ View original listing ]

----------------------------------

Description

----------------------------------

Job details
Location
Workplace
Employment
Salary

----------------------------------

Source & freshness
First observed
Last observed
Source provider

----------------------------------

Recent changes
```

Keep lifecycle history subtle.

---

# 30. Original Listing Link

This should be prominent:

```text
View original listing
```

Open the employer's source URL.

This reinforces direct-source provenance.

---

# 31. Application Behavior

OpenRole does NOT process job applications in Phase 4.

The call to action is:

```text
View original listing
```

not:

```text
Apply with OpenRole
```

---

# 32. Not-Observed Public Detail

If Job becomes:

```text
not_observed
```

the public detail page should show an obvious factual notice:

```text
This listing is no longer currently observed at its source.
```

Then:

```text
Last observed: October 7, 2026
```

Do not show the normal primary application CTA as though current.

The original source link may still exist, but label accordingly.

---

# 33. Reappeared Listing

For a currently observed Job that previously reappeared:

optional:

```text
This listing was previously not observed and later reappeared.
```

Do not overemphasize unless useful.

---

# 34. Public Change History

Show only meaningful recent changes.

Possible section:

```text
Recent listing changes

Oct 8
Workplace
Remote → Hybrid

Oct 6
Salary added
USD 90,000–110,000 / year
```

Do not show:

```text
content hashes
version IDs
PipelineRun IDs
```

---

# 35. Description Changes

For public view:

```text
Description updated
```

is enough.

Do not display giant before/after HTML blocks.

---

# 36. Historical Versions

Do not expose full version history as a developer-style timeline on public detail initially.

Use:

```text
Recent changes
```

instead.

Internal dashboard already provides the deep history.

---

# 37. Public Metadata / SEO

Every job detail page should have:

```text
<title>
meta description
canonical URL
Open Graph basics
```

derived from real Job data.

---

# 38. Page Title

Example:

```text
Backend Engineer at Example Company | OpenRole
```

Do not keyword-stuff.

---

# 39. Meta Description

Example:

```text
Backend Engineer at Example Company. Remote, full-time. Last observed directly from the employer source on October 9, 2026.
```

Generate from actual available fields.

Avoid unsupported claims.

---

# 40. Structured Data

Consider:

```text
JobPosting JSON-LD
```

only if OpenRole can accurately represent required fields.

This is useful for SEO but must be correct.

Do not fabricate:

```text
datePosted
validThrough
hiringOrganization details
salary
```

when unknown.

If required fields cannot be truthfully provided:

defer structured JobPosting data.

---

# 41. AEO / Search Engine Clarity

Public job pages should clearly answer:

```text
What is the role?
Which company?
Where?
What employment type?
What source?
When was it last observed?
```

Use semantic HTML.

Do not hide key facts behind client-only interactions.

---

# 42. Server Rendering

Prefer server rendering for:

```text
/jobs
/jobs/[jobId]
```

for:

- SEO;
- fast initial content;
- minimal client JavaScript.

Interactive filter controls may be client components.

---

# 43. Public API Safety

Do not reuse internal response models automatically.

Audit every public response field.

Exclude:

```text
source_connection_id
pipeline_run_id
raw_snapshot_id
source_observation_id
content_hash
internal metadata
quarantine details
```

unless there is a user-facing reason.

---

# 44. Rate/Load Considerations

Public traffic differs from internal dashboard traffic.

Use reasonable server-side caching/revalidation for public reads.

Unlike operational dashboard data, public jobs do not necessarily need `no-store`.

---

# 45. Public Job List Caching

Possible:

```text
revalidate every 60 seconds
```

or another modest value.

Do not hard-code a strategy before inspecting deployment/backend expectations.

Freshness remains important.

---

# 46. Public Job Detail Caching

Likewise, modest revalidation is appropriate.

A listing changing seconds ago does not necessarily require millisecond consistency.

Document the chosen freshness trade-off.

---

# 47. Internal Dashboard Caching

Do not change dashboard operational pages merely because public pages use caching.

The two surfaces have different requirements.

---

# 48. Query Parameters

Public job discovery filters should be encoded in URL.

Example:

```text
/jobs?q=backend&workplace=remote&location=berlin&page=2
```

Shareable and crawlable where appropriate.

---

# 49. Pagination

Use backend pagination.

Recommended:

```text
25 results/page
```

No infinite scroll initially.

Why?

Pagination is:

- simpler;
- more SEO-friendly;
- easier to debug;
- shareable.

---

# 50. No Client-Side Dataset Filtering

Do not download the whole job database.

FastAPI/PostgreSQL handle search/filter/pagination.

---

# 51. Company Display

Display company name.

Optional:

```text
company domain
```

on detail.

Do not expose internal Company UUID.

---

# 52. Company Logo

Do NOT build logo scraping/fetching yet.

Use typography first.

Avoid broken/incorrect company logos.

---

# 53. Landing Page

Route:

```text
/
```

Create a simple product introduction.

Goal:

explain OpenRole's difference clearly.

---

# 54. Landing Hero

Possible:

```text
Jobs with visible source freshness.

OpenRole tracks listings directly from employer ATS sources so you can see when a job was last observed and how the listing has changed.
```

CTA:

```text
Browse jobs
```

No exaggerated marketing claims.

---

# 55. Landing Content

Keep it short.

Potential sections:

```text
Direct-source listings
Freshness you can see
Historical changes
```

No giant SaaS landing-page boilerplate.

---

# 56. No Fake Social Proof

Do not add:

```text
10,000+ job seekers
500 companies
Trusted by...
```

unless real.

---

# 57. No Fake Metrics

Landing page must not invent listing/company counts.

If real aggregate counts become available later, they can be added.

---

# 58. Design Relationship to Dashboard

Public product may use the same design tokens but a lighter navigation structure.

Do not expose the admin sidebar publicly.

---

# 59. Public Navigation

Simple:

```text
OpenRole
Jobs
```

Potential:

```text
About
```

only if useful.

No dashboard link publicly unless access control/deployment context makes that appropriate.

---

# 60. Empty Job Dataset

Public `/jobs` should show:

```text
No currently observed jobs are available yet.
```

Do not expose internal setup language such as:

```text
Run source sync
```

to public users.

---

# 61. Search No Results

Show:

```text
No jobs match your search.
```

Provide clear filter reset.

---

# 62. Public Error State

Use user-facing language:

```text
We couldn't load jobs right now.
```

not internal:

```text
FastAPI returned 503.
```

---

# 63. Not Found

Unknown public Job:

```text
Job not found.
```

Historical known but not observed Job should NOT 404 merely because it isn't currently observed.

---

# 64. Accessibility

Public product should meet basic accessibility standards:

- semantic headings;
- labels;
- keyboard navigation;
- focus states;
- descriptive links;
- sufficient contrast;
- no color-only state communication.

---

# 65. Safe HTML

Continue sanitizing descriptions.

This requirement applies even more strongly on public pages.

No provider HTML reaches browser unsanitized.

---

# 66. External URL Safety

Only:

```text
http
https
```

source links should be clickable.

---

# 67. Analytics

Do NOT add third-party analytics automatically.

If product analytics are desired later, design privacy/requirements deliberately.

---

# 68. Authentication

Public discovery remains unauthenticated.

Internal dashboard access-control problem remains separate.

Phase 4 does not solve dashboard authentication unless roadmap is explicitly changed.

---

# 69. Phase 4 Suggested Task Breakdown

Continue the same micro-task process.

## Task 43 — Public API Read Model Foundation

Create safe public jobs list/detail backend contracts.

Implement:

```text
GET /api/v1/public/jobs
GET /api/v1/public/jobs/{jobId}
```

or agreed route convention.

No frontend yet.

---

## Task 44 — Public Application Shell + Landing Page

Implement:

```text
/
```

public layout/navigation and factual product explanation.

No job discovery yet.

---

## Task 45 — Public Jobs Discovery

Implement:

```text
/jobs
```

with:

- search;
- filters;
- freshness;
- pagination;
- shareable URLs.

---

## Task 46 — Public Job Detail

Implement:

```text
/jobs/[jobId]
```

with:

- current canonical listing;
- source evidence;
- freshness;
- salary/location/employment;
- sanitized description;
- original source link.

---

## Task 47 — Public Change Intelligence

Add:

```text
recent material changes
```

to public Job Detail using a safe public change-history endpoint/read model.

Do not expose internal provenance.

---

## Task 48 — SEO / Metadata / Crawlability

Implement:

- metadata;
- sitemap;
- robots decisions;
- canonical URLs;
- semantic content;
- optional JobPosting structured data only where accurate.

---

## Task 49 — Public Product E2E + Phase 4 Closure

Verify:

- search;
- filters;
- pagination;
- observed listing;
- not-observed historical detail;
- reappeared listing;
- changes;
- SEO;
- mobile;
- accessibility;
- security;
- no internal-field leakage.

Create:

```text
docs/phase-4-completion.md
```

---

# 70. Public API Principle

The public API is a product boundary.

Treat it as more stable than internal admin endpoints.

Once public consumers/pages depend on it, avoid leaking internal implementation details.

---

# 71. Public Listing Safety

A listing qualifies for default results only when:

```text
lifecycle_status = observed
AND source_connection.is_active = true
```

and has a valid current canonical JobVersion.

If an invariant is broken:

exclude/fail safely rather than publishing malformed rows.

---

# 72. Freshness Semantics

Public UI should communicate:

```text
Last observed
```

not:

```text
Last updated
```

unless discussing `source_updated_at` explicitly.

These mean different things.

---

# 73. First Seen

Potential public label:

```text
Tracked since
```

or:

```text
First observed
```

This provides useful historical context.

---

# 74. Provider Source Updated Time

Do not prominently display:

```text
source_updated_at
```

unless its provider meaning is consistent and useful.

OpenRole's own observation times are more reliable cross-source facts.

---

# 75. Trust Message

A concise reusable explanation may be useful:

```text
OpenRole checks listings directly from employer ATS sources. "Observed" means the listing appeared in OpenRole's most recent successful source checks.
```

This can appear:

- jobs discovery;
- detail tooltip;
- About/FAQ later.

---

# 76. No "Verified" Badge Yet

Despite the product concept, avoid a badge simply saying:

```text
Verified
```

because users may interpret it as:

- employer verified;
- role guaranteed;
- hiring confirmed.

Prefer:

```text
Direct source
```

and:

```text
Observed recently
```

which describe the evidence precisely.

---

# 77. Phase 4 Definition of Done

Phase 4 is complete when a public user can:

1. understand what OpenRole is;
2. browse currently observed jobs;
3. search jobs;
4. filter jobs;
5. paginate results;
6. see when each listing was last observed;
7. understand the direct-source provenance;
8. open a Job Detail page;
9. read the current canonical description safely;
10. view the employer's original listing;
11. see structured location/employment/salary facts;
12. see meaningful recent listing changes;
13. recognize when a historical listing is no longer currently observed;
14. use public pages on mobile;
15. share/copy filtered URLs;
16. load SEO-friendly server-rendered pages;
17. do all of this without exposing internal operational data.

---

# 78. Final Phase 4 Architecture

Conceptually:

```text
                   ┌─────────────────────┐
                   │  Internal Dashboard │
                   │    /dashboard/*     │
                   └─────────┬───────────┘
                             │
                             ▼
                        FastAPI
                             ▲
                             │
                   ┌─────────┴───────────┐
                   │   Public Product    │
                   │ /  /jobs /jobs/:id │
                   └─────────────────────┘
```

Both surfaces use the same backend domain truth.

But they expose different read models appropriate to their users.

---

# 79. What Comes After Phase 4

Do not decide prematurely.

Strong candidates include:

```text
Phase 5
International hiring / visa / relocation evidence
```

or:

```text
Phase 5
Second ATS provider — Lever
```

or:

```text
Phase 5
User accounts, saved jobs, and alerts
```

Choose based on what the working product reveals.

Do not add everything at once.

---

## Task 43 delivered public API contract

### Boundary and eligibility

```text
GET /api/v1/public/jobs
GET /api/v1/public/jobs/{job_id}

FastAPI → PublicJobQueryService → joined PostgreSQL projections
        → explicit public Pydantic schemas
```

Both endpoints are unauthenticated reads. They do not replace the internal
`/api/v1/jobs` contracts. No public writes, history endpoint, frontend, new provider,
schema migration, CORS expansion or authentication is included in Task 43.

Discovery requires `Job.lifecycle_status = observed`, an active SourceConnection
and exactly one current JobVersion. This deliberately uses the task's safer
inactive-source policy: disabled sources cannot keep validating listing freshness.
Company active state is not an additional eligibility filter. There is no maximum
observation age because no polling SLA is defined. Tentative absence remains
observed until the backend confirms otherwise. Reappeared observed jobs qualify.

Detail ignores discovery eligibility filters. A known not-observed job or a job
from an inactive source returns its current canonical content and factual lifecycle
timestamps. It preserves historical URLs without treating them as current discovery
results. `no_longer_observed_at` is OpenRole's confirmation time, not an exact
employer closure time; observed jobs can retain it after reappearance.

### Queries and pagination

| Parameter | Contract |
| --- | --- |
| `q` | Optional, maximum 200 characters; trimmed literal case-insensitive containment in current title **or** company name **or** location_text |
| `location` | Optional, maximum 200 characters; trimmed literal case-insensitive containment in canonical location_text |
| `workplace_type` | Optional exact value: `remote`, `hybrid`, `onsite` |
| `employment_type` | Optional exact value: `full_time`, `part_time`, `contract`, `temporary`, `internship`, `volunteer`, `other` |
| `limit` | Default 25, range 1–100 |
| `offset` | Default 0, range 0–2,147,483,647 |

Filters intersect. Empty/whitespace-only text means no text filter. `%`, `_`, and
escape characters match literally; SQLAlchemy parameterization and autoescaping
prevent SQL/wildcard injection. Description and external ATS ID are not searched.
There is no company, lifecycle, structured-country or salary query filter.
Structured geography remains null when unknown; it is never inferred.

The canonical persistence model currently stores workplace/employment as nullable
strings rather than domain enums. Public **query** enums validate the vocabulary
already used by the dashboard. Responses preserve stored nullable strings without
changing ingestion or claiming that Greenhouse supplies these values. The current
production mapper leaves unsupported enrichment fields null; filtering on them
can therefore legitimately return no results.

List responses contain `items`, accurate filtered `total`, `limit`, and `offset`.
Ordering is `Job.last_seen_at DESC, Job.id ASC`; the UUID tie-breaker makes pages
deterministic for unchanged data. First/last seen are OpenRole observation facts.
Offset pages and independent count/page reads may change under concurrent ingestion;
this API does not promise a frozen snapshot across requests.

### Explicit response fields

| Surface | Fields |
| --- | --- |
| Both list item and detail | `id`, `title`, `company.name`, `company.domain`, `location_text`, `city`, `region`, `country_code`, `workplace_type`, `employment_type`, `salary_min`, `salary_max`, `salary_currency`, `salary_period`, `first_seen_at`, `last_seen_at`, `source.provider` |
| Detail only | `company.careers_url`, `description`, `source_url`, `lifecycle_status`, `absence_first_detected_at`, `no_longer_observed_at`, `reappeared_at` |

Only the stable logical Job UUID is exposed. Job owns identity, observation times
and lifecycle facts. Current JobVersion owns canonical listing content and salary.
Company supplies display fields and SourceConnection supplies provider. Source
evidence is `source.provider` plus the detail's `source_url`; no Company or source
UUID is required for public routing.

Salary Decimals serialize as exact strings, never floats. Timestamp values retain
their timezone in ISO 8601. Nullable fields remain explicit nulls. The detail
description is returned exactly as stored, including HTML: **sanitize before
rendering**. Backend read projection does not declare provider HTML trusted.

Source/careers links must be absolute HTTP(S) URLs without embedded credentials.
The required source URL is validated again at the public boundary; an invalid
stored value fails safely. An unsafe optional stored careers URL becomes null.
The Company domain is display text, not a validated navigable URL.

Excluded from both contracts: Company/source/version/observation/run/snapshot IDs,
external_job_id, content_hash, canonical_metadata, SourceConnection.configuration,
external_account_key, reconciliation counters, storage keys, quarantine state,
internal diagnostics and full history. Descriptions remain source-authored text,
not structured internal provenance.

### Errors, invariants and efficiency

Unknown valid Job UUID: HTTP 404 with the existing `error` envelope and
`JOB_NOT_FOUND`. Invalid UUID/query/enum/length/pagination: normal FastAPI HTTP 422
validation. Missing or duplicate current versions: logged internal invariant and
HTTP 500 with generic `PUBLIC_JOBS_UNAVAILABLE`, without exception messages or
internal invariant codes. The eligible identity scope is checked before content
filters, so missing versions cannot silently disappear behind a search filter.

The partial unique `uq_job_versions_current` index prevents multiple current
versions. The defensive read boundary also rejects duplicates rather than picking
one. Existing `ix_jobs_lifecycle_status`, `ix_jobs_last_seen_at`, Job identity
uniqueness (leading source_connection_id), primary keys and current-version index
support the initial joins/eligibility/order. Containment search is a simple
parameterized PostgreSQL scan, not full-text or semantic search. No new index is
justified for the present early scale; measure actual query plans as traffic grows.

List reads use fixed-count queries for invariants, filtered count and bounded page;
detail uses one joined query. No per-job current-version/company requests, lazy
relationships, unbounded response loading or writes occur. List projections omit
descriptions; both projections omit configuration and canonical metadata entirely.

### Deployment and verification

Administrative routes and `/dashboard` still require external access control.
Adding public GET routes does not authorize publishing the entire FastAPI app,
its administrative OpenAPI documentation or its sync endpoint. Future public
traffic may require rate limits and a measured CDN/cache strategy; none is added
here. The future Next.js public server can call these endpoints without broad CORS.

Tests use PostgreSQL with rolled-back fixtures and stored Greenhouse records.
They cover discovery eligibility, freshness/tie ordering, search fields/literal
escaping, every filter value, combined filters, totals/pages, current-version
selection, exact/null salaries, historical/reappearance/inactive-source detail,
unsafe URLs, missing resources/invariants, explicit field/secret exclusion,
read-only behavior and fixed query count. Impossible duplicate-current reads use
a focused unit test because the real partial unique index forbids that state.

Task 43 verification: **PASS** (2026-10-10).

| Command / check | Result |
| --- | --- |
| `docker compose up -d postgres` (repository root) | Existing PostgreSQL running |
| `uv run pytest tests/integration/api -k public_jobs -q` (backend) | 49 passed |
| `uv run pytest tests/unit/jobs/test_public_job_invariants.py -q` | 2 passed |
| `uv run pytest tests/integration/api -q` | 159 passed |
| `uv run pytest` | 742 passed, 2 optional live Greenhouse/R2 tests skipped |
| `uv run ruff check .` | PASS |
| `uv run mypy` | PASS, 169 source files |
| Ruff formatting check on affected Python files | PASS |
| Real FastAPI/curl against isolated migrated PostgreSQL | Eight scenarios PASS: list, title search, combined filters, observed/historical/inactive-source detail, 404 and enum validation; no internal field/secret leakage |

The initial focused run found one fixture-only async lazy-loading error. Explicit
Company loading fixed it; final focused and regression runs pass. The existing
upstream Starlette TestClient/httpx deprecation warning remains. Normal tests do
not call live Greenhouse or R2. Smoke data used stored fixtures and controlled
canonical values; production mapping is unchanged. Temporary API/database were
removed, leaving the normal developer database untouched. Local HTTP evidence:
`/tmp/openrole-task43-smoke-results.json`.

## Task 44 public shell and landing foundation

Task 44 introduces the public entry point and reusable shell. At its completion,
real discovery, filters, public detail and public history were deferred to
Tasks 45–47; the Task 45 delivery is recorded below.

| URL / file | Responsibility |
| --- | --- |
| `/` via `app/(public)/page.tsx` | Static product explanation and Browse jobs links |
| `/jobs` via `app/(public)/jobs/page.tsx` | Honest forthcoming-discovery placeholder without listings or API calls |
| `app/(public)/layout.tsx` | Public header, skip link, main and footer |
| `app/layout.tsx` | Shared HTML/body, global styles and neutral brand metadata |
| `app/dashboard/layout.tsx` | Existing internal sidebar/header layout and explicit internal metadata |
| `app/not-found.tsx` | Neutral missing-page message and home return link |

The `(public)` route group does not appear in URLs. Removing the former
`app/page.tsx` dashboard redirect avoids a duplicate `/` route. No dashboard
directory moves or backend changes are needed. Public pages do not import
operational components or expose dashboard navigation, operator controls,
internal identifiers or backend configuration.

### Product message and design

The headline is **Jobs with visible source freshness.** The page explains direct
configured employer applicant-tracking-system sources, listing observation times
and preserved material changes. "Observed" means OpenRole saw a listing at its
employer ATS source; it is evidence of presence rather than confirmed hiring.
Coverage starts with configured Greenhouse sources, not every employer or ATS.
There is no promise of automatic, periodic or continuous checks. Public history
is not presented as an available visitor feature yet.

The landing has a compact hero, an Observed definition, direct-source/freshness/
history principles, a short How it works sequence, final Browse jobs CTA and
footer. Navigation includes home, Jobs and the real How it works anchor. `/jobs`
states that discovery is forthcoming instead of displaying fake listings or
presenting an unconnected page as a real empty dataset. Public copy excludes
guaranteed-open, verified-hiring, fraud-free and ghost-job claims, fabricated
metrics/social proof and internal implementation jargon.

The public shell uses the existing neutral/green tokens, system typography,
spacing and shared Button styling. A simpler editorial layout provides more
breathing room than the dashboard. No image, custom logo, dependency, animation,
new styling system or full-page client boundary is added.

### Rendering, metadata and access boundary

Both public routes are server components and static-renderable. They need no
FastAPI request, database, loading skeleton, aggregate endpoint or API client.
Landing metadata includes factual title, description and basic Open Graph
website fields. Jobs has its own placeholder metadata. Landing-specific Open
Graph does not inherit into dashboard routes, whose internal defaults and feature
title template are retained. No production site origin exists, so canonical/OG
URLs and custom social images remain omitted without a fabricated domain or new
environment variable. SEO detail, sitemap and structured data remain later work.

Each page has one primary heading, semantic landmarks, named navigation and
keyboard-accessible links. The public skip link focuses main content. Compact
header links fit mobile without a drawer; shared focus styling remains visible.

Route/layout separation is not authentication. The dashboard and administrative
FastAPI routes still require external access control when deployed; the public
landing does not expose or authorize those operational surfaces.

### Task 44 verification — 2026-10-12

| Check | Result |
| --- | --- |
| `pnpm exec next typegen` | PASS; generated route types refreshed after replacing the former root route |
| `pnpm lint` | PASS |
| `pnpm typecheck` (`tsc --noEmit`) | PASS |
| `pnpm test` | PASS: 150 tests, including eight new public-shell tests; no failures or skips |
| Clean `pnpm build` with an unreachable API base URL | PASS; `/` and `/jobs` prerendered as static content |
| Production browser checks with the API unavailable | PASS: both public routes at 1440, 768, 390 and 320 pixels without horizontal overflow |
| Keyboard navigation | PASS: visible skip/focus links, focus transfer to main, Jobs, home, Browse jobs and How it works |
| Accessibility and console | PASS: both public pages have zero axe violations or incomplete checks; normal navigation has no console messages or page errors |
| Runtime metadata and route separation | PASS: landing/Jobs metadata, internal dashboard defaults, dashboard feature title template and separate navigation |
| Global missing page | PASS: HTTP 404 with home return and no operational navigation |
| Independent frontend evaluation | PASS on attempt 1; desktop/mobile design, links, keyboard, metadata, accessibility and console, with no priority fixes |

The eight tests render actual public pages/layouts and cover header/CTA routes,
landmarks, operational-link exclusion, conservative observation wording, the
honest placeholder, neutral missing-page navigation, metadata separation and
zero fetches with an unreachable backend. Browser checks additionally inspect
generated HTML metadata and show no browser operational API requests.

Runtime inspection caught a duplicated brand suffix in the dashboard default
title. Its explicit `absolute` title preserves `OpenRole Observatory`, while
feature pages retain `%s · OpenRole`. Initial test regular expressions were
adjusted to the existing TypeScript target; final type checking passes without
ignored errors. Cached route types were regenerated rather than retained from
the removed root route.

Backend code, dependencies and environment files are unchanged by Task 44; no
backend tests were rerun. The normal frontend and FastAPI services still return
HTTP 200 for home, Jobs, dashboard, health, readiness and public jobs reads.
Build/test/browser evidence and desktop/mobile screenshots are stored under
`/tmp/openrole-task44-aI3S5GpQ/`. Real discovery was pending at Task 44 completion.
The temporary production test server was stopped after verification; the normal
frontend remains available on port 3000. Independent evaluation screenshots also
cover 375 pixels and both public pages at desktop/mobile sizes.

## Task 45 public job discovery

Task 45 replaces the Task 44 `/jobs` placeholder with real public API-backed
discovery. At Task 45 completion, full detail and history remained Tasks 46–47. No backend contracts,
database schema, ingestion behavior, dependencies or environment settings change.

```text
Native GET form / shareable URL
    ↓ q, location, workplace, employment, page
Next.js async server page
    ↓ normalize URL, then listPublicJobs()
GET /api/v1/public/jobs
    ↓ PublicJobQueryService
PostgreSQL eligibility + intersecting filters + count + bounded ordered page
    ↓ validated public allowlist projection
Server-rendered result articles + total-based pagination
```

### Search, filters and pagination

`q` matches literal text case-insensitively in title, company name or canonical
location text. `location` matches location text only, with no structured-city or
country inference. Descriptions and external ATS IDs are not searched. Text is
trimmed and bounded to 200 Unicode code points; ordinary internal whitespace is
preserved. Empty values are omitted.

Frontend URL `workplace` maps to backend `workplace_type` with `remote`, `hybrid`
or `onsite`. URL `employment` maps to `employment_type` with `full_time`,
`part_time`, `contract`, `temporary`, `internship`, `volunteer` or `other`. Filters
intersect; no lifecycle, provider, country or salary controls are introduced.
The API owns observed/active-source/current-version eligibility and freshness
ordering. The frontend neither filters returned lifecycle facts nor sorts jobs.

The native GET form requires no custom filter client component. Explicit Search
or Enter submits the controls, without a page field, resetting to page one.
The server redirects malformed, repeated, blank or unnormalized parameters to
the normalized local URL before fetching. Canonical parameter values, rather
than parameter order or encoding, determine whether normalization is required.
Previous/Next links retain all committed filters; reload, sharing and browser
Back/Forward use the same URL state.
The form disables autocomplete restoration to prevent newer draft values from
being restored over older committed URL filters by browser history. A query key
also remounts the server-rendered form when Next.js navigation changes URL state;
no custom filter client component is required.

Pages contain 25 results; offset is `(page - 1) * 25` within PostgreSQL's bound.
The displayed result total and page count come from the filtered backend total.
Excessive page requests redirect to the last available page, or page one when
total is zero, retaining filters. An empty item page within range is recoverable:
independent count/page queries can differ during concurrent ingestion, so empty
items alone do not trigger a redirect. Offset pages are not a frozen snapshot.

### Presentation and public boundaries

The page reuses Task 44's public shell and neutral/green typography, spacing and
Button system. Labeled filters stack on mobile; results use semantic articles
with wrapping title links, company, location and a prominent source-evidence
column. Missing location reads "Location not stated". Known workplace/employment
values use shared labels; unknown or missing values are omitted without inference.
Production Greenhouse mapping can leave these fields null, so type filters can
legitimately have no matches.

Salary uses the existing exact-decimal formatter only with an amount, a currency
supported by the runtime's Intl currency vocabulary and a recognized period. Zero bounds remain zero; incomplete
salary data is omitted instead of showing a technical placeholder or inventing
units. No float conversion is introduced. **Last observed** uses `last_seen_at`
with the established absolute UTC formatter and semantic `time` element. There
is no client timer, hydration-dependent relative date or employer-update claim.
**Direct source · Greenhouse** identifies the observed employer ATS provider,
not a guarantee of current hiring or universal source coverage.

Distinct public TypeScript types match Task 43. The server-only API module checks
response shape, explicit nulls, timestamps, decimal strings, pagination and detail
identity. It projects an allowlist, including nested company/source objects, so
unexpected internal fields are dropped. It reuses the shared four-second timeout
and `cache: no-store`: the current small deployment does not need a query cache,
and uncached reads avoid introducing another delay in observation visibility.
API configuration remains private to the Next.js server; browsers do not call
FastAPI directly. No backend URL is serialized into public output.

Source text is escaped by React. Cards contain no descriptions, internal IDs,
operator actions, Apply/Save controls or recommendation labels. The list uses one
bounded public read, rather than administrative data or per-result detail calls.

### States and detail preview

Zero-total unfiltered results, zero-total filtered results, changing in-range
pages and API failures remain distinct. Expected failures preserve the filter
form and use public-safe copy with a full-request retry; they do not become
zero-job datasets or expose error codes/exception text. An error boundary handles
unexpected page errors. Route loading displays neutral skeletons without fake
employers or results.

Selecting a listing opens `/jobs/[jobId]`. The minimal preview reads public
detail, displays only its real title/company and a forthcoming-full-detail note,
and links back to public Jobs. Known historical or inactive-source listings stay
addressable without being presented as currently observed. Missing/invalid IDs
have a public not-found state; unavailable previews have public retry copy.
Descriptions, original source actions, lifecycle detail and history remain later
work. The landing's final CTA now describes available discovery; its history
copy still states that public history is forthcoming.

Jobs metadata describes actual search and source observations. The preview has
its own title/description. No production origin, canonical URL, SEO strategy,
new image, dependency or filter state framework is added.

### Task 45 verification — 2026-10-12

| Check | Result |
| --- | --- |
| Focused public suites | PASS: 32 tests, including 24 new discovery cases and eight updated shell cases |
| `pnpm lint` | PASS |
| `pnpm exec next typegen` | PASS; generated types refreshed for the new preview route |
| `pnpm typecheck` (`tsc --noEmit`) | PASS |
| `pnpm test` | PASS: 174 tests, zero failures or skips |
| Clean `pnpm build` with an unreachable API base URL | PASS; `/` remains static, `/jobs` and `/jobs/[jobId]` are dynamic |
| Real public API fixture checks | PASS: 20 filter/pagination scenarios plus historical/inactive detail reads |
| Production browser results | PASS: exact API page identities/order/totals for default, title/company/location search, location filter, all three workplace values, all seven employment values and combined filters |
| URL/navigation behavior | PASS: Enter trimming/blank cleanup, page reset, retained pagination, shared second-tab URL, Back/Forward controls/results, excessive-page clamps and invalid/repeated parameter normalization |
| Result/preview facts | PASS: exact salaries, zero and partial values, missing/unknown canonical fields, last-observed UTC time, direct-source labels and minimal public-only preview links |
| Responsive checks | PASS: 1440, 768, 390 and 320 pixels, including long escaped source title/location on page three |
| Accessibility and console | PASS: discovery desktop/mobile, preview, empty and unavailable states have zero axe violations/incomplete checks; normal browser console/page errors are empty |
| Actual isolated FastAPI outage/recovery | PASS: safe error copy, retained filters, no fabricated zero total, preview failure and full-request retry after restart |
| Loading | PASS: actual delayed fresh navigation captured the skeleton and transition to 25 real results; loading markup is also covered by rendering tests |
| Independent frontend evaluation | PASS on attempt 1, with no priority fixes; additional 375-pixel coverage, filters/results/long-card screenshots, URL history, keyboard, preview and empty states |

The new tests exercise query normalization/offset bounds, filter vocabulary and
page counts, public-only API calls/field projections, null/date/decimal/URL and
detail-identity validation, missing/error responses, exact formatting and real
rendered controls/cards/pagination/loading/empty/error/preview states. Extra
internal fields and adversarial source text cannot become public UI.

Browser verification found a real native-form history issue: Back restored the
older URL/results but retained newer draft inputs. Disabling form autocomplete
restoration corrected the reproduced text/select mismatch; final checks confirm
all four controls and results on Back/Forward. A rendering assertion protects
that form setting. Initial render assertions were also made independent of
attribute order and stopped rejecting the legitimate search term "backend" in a
retained error-state form. Final suites pass.

Loading capture depends on navigation timing and whether a destination is ready.
A fresh delayed transition was captured successfully; repeat attempts that
required the transient skeleton on every navigation could miss it. These harness
attempts did not require an implementation change; the actual loading component
and successful skeleton-to-results transition remain verified.

Manual verification used an isolated Alembic-migrated PostgreSQL database with
58 eligible listings across two companies plus excluded historical/inactive-source
listings. Stored Greenhouse fixture records went through the existing new-job
persistence service, with controlled canonical salary/type values for presentation
coverage. No live ATS/R2 requests occurred, production mapping was unchanged and
no fixture rows entered the normal developer database. Evidence is under
`/tmp/openrole-task45-RIGQjO2D/`, including API cases, browser/state scripts and
logs, test/build output, desktop/mobile/loading/empty/unavailable screenshots.

Backend source hashes, shared client/styles and dependency manifests remain
unchanged. No backend tests were rerun for this frontend-only task. Full detail
was pending at Task 45 completion; Task 46 delivery is recorded below.

Task 45 verification verdict: **PASS**. The temporary production frontend/API
and isolated database were removed after evaluation; the database's absence was
confirmed through PostgreSQL. Normal Next.js on port 3000 and FastAPI on 8000
remain available. Home, discovery, dashboard/jobs, health, readiness and public
Jobs returned HTTP 200 after cleanup. The normal public dataset is still empty
and unchanged; all populated screenshot rows came from isolated verification.

## Task 46 public current job detail

Task 46 replaces the title/company preview with a current public detail page at
`/jobs/[jobId]`, retaining the public shell. It reads only the Task 43 public
Job Detail API through `getPublicJob()`, the existing strict validator and explicit
public projection. No backend, schema, public API contract or dependency changes
are needed. Public change intelligence remains Task 47; structured data and
canonical SEO remain Task 48. This is not Phase 4 completion.

### Listing and observation evidence

The page shows current canonical title, company, location, known canonical
workplace/employment values, exact salary amounts, a full safe description and a
source action. Missing location says `Location not stated`; unknown type fields
are omitted. Partial structured salary is useful on detail: known decimal bounds
(including zero) retain exact values, while missing/unrecognized currency or
period receives an explicit unavailable-unit qualifier. No currency conversion,
frontend geography inference or description salary parsing occurs. Discovery's
existing stricter salary-card policy remains unchanged.

The prominent **Last observed** UTC time comes from `last_seen_at`, evidence of
OpenRole's source observation rather than an arbitrary update date. **First
observed** uses `first_seen_at`, not an inferred employer publication date.
`Direct source · Greenhouse` identifies direct employer ATS evidence; explanatory
copy avoids employer verification or confirmation of hiring.

Current lifecycle labels follow the backend: `Observed` and `Not currently
observed`. Tentative absence stays Observed. Confirmed absence adds a restrained
notice plus optional `Absence confirmed` time, which describes OpenRole's
confirmation rather than employer closure. An observed job with `reappeared_at`
has secondary `Previously not observed · Reappeared …` context. Its historical
`no_longer_observed_at` is not presented as a current absence warning. Known
historical and inactive-source jobs remain addressable; source-active status is
not part of this detail contract, so Observed never implies discovery eligibility
or promised ongoing monitoring.

Observed jobs offer **View original listing**; absent jobs offer **Check original
source**. Both open the actual safe source URL in a new tab with `noopener
noreferrer` and a visible new-tab hint. There is no OpenRole application flow.
Only absolute credential-free HTTP(S) is clickable. Company domain remains plain
escaped text. The required safe source-URL API contract remains strict: an unsafe
or null successful payload is rejected into the unavailable state rather than
trusted as a valid job. The component also guards its CTA defensively.

### Shared description safety

Public and dashboard detail share `sanitizeJobDescription` and `JobDescription`.
The established `sanitize-html` allowlist retains paragraphs, line breaks, lists,
headings, strong/emphasis, blockquotes and safe links. Scripts, styles, event
handlers, images, dangerous embeds and form content are removed. Arbitrary
provider styles, classes and IDs do not survive. Anchors permit only absolute
credential-free HTTP(S) and receive secure new-tab attributes. All source h1–h6
normalize to h3 under the Description h2, preserving one page title and consistent
heading hierarchy. Only the sanitized result reaches the HTML injection point.

Empty, whitespace-only and script-only descriptions get a friendly public
fallback. Plain multiline text preserves line breaks. The dashboard's default
empty text stays unchanged; it receives the same shared heading/security behavior.
No separate public sanitizer policy is introduced.

### Request sharing, metadata and missing jobs

The server-only `getPublicJobDetail()` wraps the existing API call with React
`cache()`. Layout, metadata and page share one result within a server request.
Reads retain Task 45's deliberate `no-store` and four-second timeout; subsequent
document requests read again. This is request memoization, not persistent listing
caching. The shared client's AbortSignal bypasses automatic Next fetch deduplication,
so the explicit wrapper prevents redundant metadata/page API calls. Tests outside
React server rendering verify read outcomes; actual production HTTP request
counts verify memoization and freshness.

Dynamic metadata uses real title/company, known location/types and the UTC last
observation. The root template supplies OpenRole once. Not-observed metadata
identifies a historical listing without automatically labeling it Closed or
Expired. Missing jobs use `notFound()`; API failure gives generic unavailable
metadata and safe retry copy rather than a false 404. No description HTML,
JobPosting JSON-LD, fabricated production origin or canonical URL is included.

The detail route lives in `(public)/(job-detail)/jobs/[jobId]`. This group adds no
URL segment and separates detail from discovery's `/jobs/loading.tsx`. Its async
layout awaits the shared read and rejects missing jobs before rendering children,
allowing HTTP 404 before headers stream. The feature not-found boundary sits in
the parent `jobs/not-found.tsx`, which catches missing-job errors from the child
layout. Next metadata defaults are unchanged. See
[Next.js not-found response semantics](https://nextjs.org/docs/app/api-reference/file-conventions/not-found).

Initial detail documents wait for the bounded lookup. The detail route retains a
title/detail/description skeleton; on client navigation its visibility depends on
prefetch, loading-boundary reuse and timing. A skeleton is not promised on every
navigation. The page and description stay server-rendered; only unexpected-error
reset interaction is a client boundary. `Back to jobs` goes to `/jobs`, and
normal browser Back preserves discovery URL filters without global return state.

Public output omits source/company/observation/run/snapshot IDs, hashes, version
numbers, lifecycle counters, metadata/configuration and historical timelines. The
public job UUID is used for routing only, not a visible diagnostic field.

### Task 46 verification — 2026-10-12

| Check | Result |
| --- | --- |
| `pnpm test` | PASS: 191 tests, zero failures/skips; 17 added versus Task 45 |
| Focused detail/discovery/shared-description tests | PASS: 48 tests, including current lifecycle, exact partial salaries, metadata, unsafe URLs/HTML and actual layout outcomes |
| `pnpm lint` | PASS |
| `pnpm exec next typegen`, then `pnpm tsc --noEmit` | PASS; standalone TypeScript also passed after the final build |
| `OPENROLE_API_BASE_URL=http://127.0.0.1:9 pnpm build` | PASS with FastAPI unreachable; detail/discovery remain dynamic, landing static |
| Real public API/production documents | PASS: 11 persisted scenarios; one API read shared by layout/page/metadata, fresh read on a separate document request |
| Missing identity HTTP responses | PASS: valid missing and malformed UUIDs return 404; browser/curl/empty User-Agent covered; malformed UUID sends no API request |
| Public missing UI | PASS after framework hydration: feature-specific missing text, public shell and return link; zero axe violations/incomplete checks |
| Observed/sparse/not-observed/reappeared | PASS: real canonical fields, exact salaries, clear absence notice/confirmation, secondary reappearance and no old-confirmation current warning |
| Tentative absence/inactive source | PASS: stored Observed state retained without inferring discovery eligibility, closure or monitoring cadence |
| Description and URL security | PASS: malicious content removed, source headings normalized, plain multiline text readable, script-only fallback, unsafe stored source fails safely |
| Actual original-source navigation | PASS: controlled employer destination opens in a new tab with `window.opener === null`; no live ATS requests |
| Responsive/keyboard/accessibility | PASS: normal/sparse/absent/long cases at 320, 390, 768 and 1440 pixels; no horizontal overflow; source CTA focusable; checked states have zero axe violations/incomplete checks |
| Discovery return/navigation | PASS: listing selection opens current detail; browser Back restores committed search/type URL and controls |
| Browser console | PASS: no normal console messages, hydration warnings or uncaught browser errors |
| Real isolated API outage/recovery | PASS: safe unavailable copy/metadata, no false 404, full-request retry recovers real facts; normal FastAPI/database left running |
| Loading | Component/render tests PASS; delayed client-navigation capture did not observe a transient skeleton before the real page arrived; visibility is timing-dependent |

The initial metadata-blocking proposal still returned HTTP 200 for missing jobs:
Next handles metadata's not-found result within rendering, while the ancestor
loading boundary can commit successful headers. Actual production verification
caught this despite passing component tests. The final route group and async
existence guard correct the status without a backend change, proxy or duplicate
lookup. The global metadata override was removed. Missing initial documents use
Next's error-recovery shell with the feature fallback in the RSC payload;
browser verification confirms the public not-found page after hydration.

Moving the route initially left generated TypeScript references stale; route type
generation corrected them. Running standalone TypeScript concurrently with a
build also briefly observed a generated file while it was being regenerated;
serial post-build TypeScript passed. These were generated-output timing issues,
with no remaining source type errors. Manual loading capture timed out twice;
no product change was made solely to force a transient screenshot.

Verification used an isolated, Alembic-migrated PostgreSQL database and the real
FastAPI application/public projection. Eleven jobs cover observed, sparse,
confirmed absence, reappearance with retained historical confirmation, tentative
absence, inactive source, plain partial salary, missing currency, script-only
content, long malicious-looking text, and a deliberately corrupted source URL.
Stored Greenhouse fixtures went through existing persistence; controlled
canonical content and lifecycle timestamps provide presentation coverage. The
unsafe source URL was introduced only in the isolated database to exercise the
read boundary. No live ATS/R2 requests or normal-database fixture writes occurred.

Evidence is under `/tmp/openrole-task46-Js55T5Up/`: final tests/build/typecheck
logs, HTTP request/status/count checks, browser/state/loading scripts, accessibility
results, scope hashes and desktop/mobile screenshots. Initial unsuccessful QA
attempts are retained alongside final passing runs. Source comparison records
25 entries, including three old detail paths removed by the route move. Backend,
public API contracts/client, dependency manifests, Next configuration and shared
global styles are unchanged. No backend test suite was rerun for this
frontend-only task.

Independent frontend evaluation: **PASS on attempt 1**, with no required
revisions. It reviewed all eleven cases, 320/375/390/768/1440-pixel containment,
metadata, safe original-source new-tab navigation, keyboard skip/focus, discovery
Back, public unavailable/missing states, representative axe audits and normal
console output. The review noted one optional refinement: sanitized anchors
without href retain link coloring/underlining even though they are inert; the
shared security policy correctly prevents navigation, and no separate public
sanitizer behavior was introduced.

Task 46 verification verdict: **PASS**. The final revised layout also passed a
real isolated API stop/restart and retry check. Temporary Next.js (3016), FastAPI
(50211) and the isolated database were removed; PostgreSQL confirmed the database
no longer exists. Normal Next.js (3000) and FastAPI (8000) remain running. Home,
Jobs, dashboard/jobs, health, readiness and public Jobs all returned HTTP 200
after cleanup; the normal public dataset remains empty and unchanged. Screenshot
listings came only from the removed isolated verification database. Task 47 was
not started.

## Task 47 public change intelligence

Task 47 adds `GET /api/v1/public/jobs/{job_id}/changes` and **Recent listing
changes** on current public detail. It uses persisted JobChangeEvents, not a
new diff engine or frontend comparison of JobVersions. No schema migration,
ingestion/persistence mutation or internal API contract change is introduced.
Task 48 SEO, sitemap, crawlability and structured-data decisions were pending
at Task 47 completion; their delivery is recorded below.

### Public contract and curated fields

```json
{
  "job_id": "public job UUID",
  "items": [
    {
      "observed_at": "2026-10-08T12:00:00Z",
      "changes": [
        {
          "field": "workplace_type",
          "change_type": "modified",
          "old_value": "remote",
          "new_value": "hybrid"
        },
        {
          "field": "description",
          "change_type": "modified"
        }
      ]
    }
  ],
  "limit": 10
}
```

`limit` bounds **complete transition groups**, default 10 and maximum 50. There
is no offset, total, cursor or unlimited-history mode. At most nine curated
meanings occur per group. Groups order by observation time descending, then
internal destination/source version UUIDs descending for stable ties. Those keys
are never exposed. Distinct transitions with the same timestamp remain separate;
the UI must not merge them merely by date/time. Within groups the fixed order is:

```text
title, location_text, city, region, country_code,
workplace_type, employment_type, salary, description
```

Text changes have strict string-or-null before/after values. Canonical location
fields stay separate, avoiding geography inference or duplicate interpretation.
`added`, `removed` and `modified` remain machine values; clients own English labels.
The public schema never reuses the broad internal event JSON/read model.

Source URL and canonical metadata changes are excluded entirely, including
excluded-only transitions before selection/limits. Routine URL churn has no
useful material role meaning here. Provider/debug metadata is not a public
product field. Description changes have only field/type markers: no old/new keys,
full bodies, historical HTML, links, snippets or description diffs are returned.
Event/version IDs, version numbers, creation times, observation/run/snapshot IDs,
hashes, source/company IDs and operational configuration are absent. The outer
logical job UUID is public routing identity only.

Known observed, not-observed and inactive-source jobs remain addressable. A known
job with no curated changes returns HTTP 200 with empty `items`, including initial
Version 1 or excluded-only history. Unknown jobs return the existing JOB_NOT_FOUND
404 envelope. Malformed stored public values fail visibly with generic unavailable
copy instead of being converted into debug text.

### Salary context and event source of truth

Any persisted salary_min/max/currency/period event in a transition triggers one
semantic Salary entry. Two conditional joins select only those four scalar fields
from each immutable version, so unchanged bounds/currency/period remain known.
This is context enrichment of stored events, not recomputing differences:
without a salary event, no Salary change is emitted. Historical descriptions,
metadata, hashes and complete versions are not loaded. Version ownership is
checked when enriching salary so a corrupted foreign-job reference cannot expose
another job's salary context.

Salary values are typed objects `{min, max, currency, period}` with explicit
nulls and exact Decimal strings. A null object means all four components are
absent. Added/removed classification describes any structured salary-information
presence; currency-only information therefore counts as information. Otherwise
the semantic type is modified. The frontend displays amounts with exact shared
formatting and missing-unit qualifiers, or explicit amount/currency/period facts
for unit-only history. No conversion, frontend salary parsing or inferred units
occurs.

The query uses two SELECT statements regardless of group/event count: an identity
check and one bounded grouped-event query with scalar salary joins. The latter's
subquery limits eligible transitions before fetching complete fields. SQL CASE
returns only text-field event values; description bodies never enter the result.
There are no per-event lazy loads or version queries. Pure projection combines
salary rows, validates public values and consistent observation timestamps, and
constructs explicit public schemas. All operations remain read-only.

### Public presentation and failure isolation

The section follows the current listing/description, preserving Task 46's primary
layout/existence read and metadata. An independent server child/Suspense boundary
loads history; its pending copy/skeleton affects only the secondary section.
API transport/status/validation failures produce `Change history is unavailable
right now.` The current title, lifecycle, description, source CTA and metadata
remain useful. Successful empty history is a distinct subtle state.

UTC group headings use absolute dates with minute precision. `observed_at` maps
persisted `detected_at`, supplied by the accepted source observation; it does not
establish the employer's exact action time. Before/After labels describe direction
without relying on red/green styling or arrow icons. Safe canonical text is React
escaped; known enum values are humanized, nulls/blank text say `Not stated` and
unknown enum values say `Unavailable`. Description markers never render historical
HTML. Long title/location/salary values wrap on mobile without a developer-style
version timeline.

A separate typed server-only client validates and projects the response allowlist.
It uses the existing uncached, four-second policy. History is not part of the
primary React cache or metadata, preventing an extra history read from delaying
existence/metadata resolution. No frontend re-diffing, admin API calls, polling,
new client state, dependencies, SEO changes or public full-history pages are added.

### Task 47 verification — 2026-10-12

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/api -k public` | PASS: 64 tests, 110 deselected |
| `uv run pytest` | PASS: 770 tests, two gated live-service skips; 28 new backend cases |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS |
| `uv run mypy` | PASS: strict checking of 173 source files |
| `pnpm test` | PASS: 206 tests; 15 new frontend cases |
| Focused frontend history/detail/discovery/shell tests | PASS: 46 tests |
| `pnpm lint`, `pnpm tsc --noEmit` | PASS |
| `OPENROLE_API_BASE_URL=http://127.0.0.1:9 pnpm build` | PASS with FastAPI unreachable; public detail remains dynamic |
| Actual public changes API | PASS: eight persisted history scenarios match API documents, with no historical bodies or private fields |
| Request reuse/freshness | PASS: one primary and one changes read per production document; separate document requests read both again |
| Primary missing resources | PASS: unknown/malformed primary remains HTTP 404 and never requests changes |
| Loading isolation | PASS: both HTTP streaming and a browser DOM observer saw current listing content with the secondary changes skeleton before history resolved |
| Real changes-only HTTP 500 | PASS: current title/source action/metadata remain; distinct safe unavailable copy, no backend diagnostics, reload recovery |
| Changed/empty/historical/inactive/excluded-only history | PASS: newest groups, complete Salary meanings, description markers, historical access and honest empty states |
| Partial/unit-only salary | PASS: exact decimals/zero, unavailable-unit qualifiers and readable unit-only facts |
| Mobile/long text | PASS: changed, long, unit-only and empty histories at 320/390/768/1440 pixels; no horizontal overflow or source-text execution |
| Accessibility/console | PASS: checked states have zero axe violations/incomplete checks; Before/After meaning, keyboard source action, no normal console messages or browser errors |

Automated tests generate event histories through the existing changed-job
persistence service over stored Greenhouse records. They cover curated fields,
added/removed/modified text, complete salary context, four-field salary grouping,
description/body exclusion, skipped metadata/URL-only transitions before limits,
same-time distinct groups, known initial/empty/historical/inactive jobs, unknown
404, bound validation, constant two-query reads and unchanged registered tables.
Corrupt structured text or foreign-job salary references fail safely. Pure tests
cover exact values, markers, semantic salary presence and deterministic grouping.
Frontend tests validate/project the public contract and render real history,
pending/empty/unavailable states, escaping, types, partial salaries and fallback.

No behavioral test failures occurred. Ruff initially flagged calls to UUID in a
test helper's default arguments; moving immutable defaults to named constants
resolved it. Formatting checks caught the helper layout during that adjustment;
the final whole-backend format check passes. The only backend warning is the
existing Starlette TestClient/httpx deprecation. Live Greenhouse/R2 checks remain
explicitly gated and were not run.

Manual verification used an isolated Alembic-migrated PostgreSQL database and
real FastAPI/public projections. Eight scenarios cover changed, no curated
changes, confirmed absence, inactive source, partial zero salary, unit-only
salary, excluded-only churn and long malicious-looking historical text. Persisted
events come from the existing version-transition service; no frontend or request-
time diff is substituted. Controlled fixture-only delay/failure middleware tests
secondary resilience without stopping normal FastAPI. No live ATS/R2 requests
or normal-database fixture rows are involved. Evidence is under
`/tmp/openrole-task47-MiOAkqGX/`, including checks/logs, streamed initial HTML,
browser observer/state scripts, accessibility results and desktop/mobile captures.

Independent frontend evaluation: **PASS on attempt 1**, with no priority fixes.
It reviewed all eight real histories, 320/375/390/768/1440-pixel containment,
semantic field/value/group/date presentation, exact/partial/unit-only salary,
description markers, no historical HTML/provenance/source-URL anchors, keyboard
focus and representative axe/console results. Its own changes-only failure test
preserved current title/source/metadata; removing the fixture control and reloading
recovered recorded groups. The review closed its browser and left no controls.

Task 47 verification verdict: **PASS**. Temporary Next.js (3017), FastAPI (52397)
and the isolated database were removed; PostgreSQL confirmed the database no
longer exists. Normal Next.js (3000) and updated FastAPI (8000) remain running.
Home, Jobs, dashboard/jobs, health, readiness and public Jobs return HTTP 200;
the new normal changes endpoint returns the expected JOB_NOT_FOUND 404 for an
unknown UUID. The normal public dataset remains empty and unchanged. Populated
screenshots came only from isolated verification.

Source comparison records 22 created/modified files. Existing ingestion, diff,
models, migrations, internal history contracts, primary detail cache/layout,
metadata builder, shared API client, dependency manifests, environment files and
global styles were not changed. Task 48 was not started.

## Task 48 SEO and crawlability

Task 48 adds explicit server-side site-origin configuration, canonical URLs,
factual public Open Graph metadata, lifecycle/query indexing, dashboard noindex,
robots and a runtime sitemap. No new job-product feature, slug, account, analytics,
image generation, ingestion behavior or schema migration is introduced. Task 49
phase closure is recorded after this task's verification section.

### Site origin, metadata and index policy

`OPENROLE_SITE_URL` is the single canonical origin, supplied at build and server
startup. Paths, query strings, fragments, credentials and unsupported schemes are
rejected; production requires HTTPS and rejects localhost/common loopback hosts.
Development can explicitly configure local HTTP. No request Host/deployment name,
localhost or example-domain fallback is treated as a production origin. Missing
or invalid settings disable indexing and absolute URLs while preserving the UI.
Static landing metadata requires rebuild/restart when configuration changes.

Configured Home/default Jobs are index/follow. Meaningful search/location/type
filters and page > 1 use noindex/follow, always canonical to `/jobs`. Existing
query normalization removes unsupported/incidental values; GET-form discovery
and pagination behavior are unchanged. There are no SEO filter landing pages or
rel=prev/next tags. Observed meaningful detail uses index/follow and its stable
public UUID URL, ignoring incidental query parameters; historical detail remains
HTTP 200, self-canonical and noindex/follow. Reappeared observed detail follows its
current state, not its retained historical absence timestamp. Unavailable detail
has no job canonical/social URL and noindex/nofollow; unknown jobs retain normal
HTTP 404 without fabricated Job metadata.

The root supplies metadataBase only from explicit configuration and safe default
noindex/nofollow. Public pages override this deliberately. Titles use the existing
brand template once; descriptions use real title/company, known location/types
and last observation, with no awkward absent-field placeholders or doubled
abbreviation punctuation. Historical descriptions identify historical listings,
not employer closure. Open Graph uses website, factual title/description, public
canonical URL and OpenRole siteName. No unsupported hiring/verification claims,
new social account, image or logo is invented. Metadata uses the shared primary
request cache; recent changes do not alter it or add metadata reads.

Dashboard layout supplies inherited noindex/nofollow, and robots excludes base/
child dashboard and API paths. Public navigation and the sitemap never link to
operational pages. Robots is not access control and a blocked crawler may not
see noindex; existing external dashboard protection remains necessary. See
[Google's noindex guidance](https://developers.google.com/search/docs/crawling-indexing/block-indexing).

### Sitemap ID projection and runtime generation

The existing public discovery API returns full summaries, small offset batches,
repeated count/invariant reads and mutable freshness ordering. After the requested
stop-and-propose step, Task 48 adds a narrower endpoint:

```text
GET /api/v1/public/jobs/sitemap?limit=1000&after=<public-job-UUID>
{items: [{id}], next_after: UUID|null, limit: 1000}
```

Limits are 1–1000, default 1000. Static route registration precedes the dynamic
job-ID route. Eligibility matches public discovery: observed jobs, active source,
and exactly one current version. One scalar SELECT per batch counts current
versions without selecting titles/descriptions/salary/configuration/history.
Missing/duplicate current-version states fail through generic public read errors.
A one-row lookahead provides continuation without totals; stable UUID ordering
avoids using mutable observation timestamps as pagination position. Only public
routing IDs and the continuation ID are returned, never operational identifiers.
There are no writes or migration requirements.

The dynamic Next sitemap walks every validated batch and includes `/`, `/jobs`
and all eligible stable detail URLs. It never reads PostgreSQL directly or calls
admin/history APIs. The client projects only IDs, validates bounds/order/cursor
progress and rejects stale/duplicate batches. No lastModified, priority or
frequency is invented. Not-observed/inactive jobs drop out of future generations;
reappearance restores eligibility for active sources. Detail indexing is status-
based because the public detail contract has no source-active flag; known
inactive observed detail remains addressable/indexable but is not promoted by
the sitemap.

Each batch reflects committed state at its query; concurrent ingestion can alter
membership during a walk. Later generation re-evaluates current eligibility,
without claiming a database-wide snapshot. The file has the standard 50,000-URL
bound, including two static entries; overflow fails explicitly instead of
truncating. Multiple sitemaps are future work if that size is reached. Any failed
walk becomes a generic runtime HTTP 500, not a partial or falsely complete XML
response. Missing origin produces empty XML, no API read and no sitemap robots
advertisement. Both robots/sitemap are dynamic; no live backend is needed during
build. See [Next's sitemap convention](https://nextjs.org/docs/app/api-reference/file-conventions/metadata/sitemap).

### JobPosting decision and factual field matrix

**Decision B — JobPosting JSON-LD DEFERRED.** Google's job rich-result eligibility
requires the employer's original datePosted; the public model does not contain it
and the current Greenhouse mapper sets source_published_at to null. Neither
first_seen_at nor last_seen_at establishes publication. No validThrough is
inferred from absence, last observation or an arbitrary expiry period. See
[Google's required properties](https://developers.google.com/search/docs/appearance/structured-data/job-posting).

| Candidate | Available fact | Task 48 treatment |
| --- | --- | --- |
| title | Current canonical text | Metadata/visible heading; no JSON-LD |
| description | Nullable untrusted source content | Shared sanitized visible renderer; no historical/unsafe script markup |
| hiringOrganization.name | Company name | Factual title/visible content |
| sameAs/logo | Domain is optional bare text; no trustworthy logo | No invented URL/logo |
| jobLocation | Nullable canonical geography; free text often only value | No parsing into invented addresses |
| jobLocationType | Optional canonical workplace | No remote/hybrid inference or eligibility assertion |
| employmentType | Optional canonical value | Existing humanized visible facts; no unsupported schema mapping emitted |
| baseSalary | Optional exact structured amounts/currency/period | Visible exact values; all salary JSON-LD omitted with JobPosting deferral |
| url | Configured origin + public UUID | Canonical and Open Graph URL |
| datePosted | Unavailable reliable employer publication date | Never substitute first observation |
| validThrough | Unavailable employer expiry | Never invent from observation/absence |
| identifier | Public routing UUID is not employer-owned ID | No identifier markup or exposure of external source IDs |
| applicantLocationRequirements | Unavailable explicit restrictions | No country inference |
| observed lifecycle/timestamps | OpenRole evidence | Index policy/factual copy, not employer publication/closure facts |

No JSON-LD script/serialization helper is added solely to return null, and no
optional decorative WebSite/Organization schema is introduced. Tests and actual
HTML inspection instead verify absence of JobPosting/datePosted/validThrough and
operational fields. Structured salary would require explicit factual currency/
period/amounts plus a viable JobPosting model; it is not emitted in this task.

### Task 48 verification — 2026-10-12

| Check | Result |
| --- | --- |
| Backend `uv run pytest tests/integration/api -k public` | 73 passed; 110 deselected |
| Backend `uv run pytest` | 780 passed; 2 intentionally gated live Greenhouse/R2 tests skipped |
| Backend `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` | Passed |
| Frontend `pnpm test` | 220 passed, including 14 new metadata/sitemap cases |
| Frontend `pnpm lint`, `pnpm tsc --noEmit` | Passed; final lint has no warnings |
| Frontend `pnpm build`, configured and unconfigured origin | Both passed with FastAPI unreachable |

Nine new PostgreSQL API cases verify sitemap eligibility, inactive/historical
exclusion, bounded cursor traversal, a single SELECT, public projection,
missing-current-version failure and parameter validation. The existing invariant
unit test now also covers a duplicate current version in the sitemap read.
Frontend cases cover explicit origin validation, canonical/index policy,
historical/reappeared/sparse/hostile metadata, punctuation, robots, complete
multi-batch traversal, malformed/stalled batches, later-batch failure and overflow.

Production HTTP and browser checks used an isolated, migrated PostgreSQL
database and real FastAPI routes with 36 eligible listings plus two historical/
inactive exclusions. The resulting sitemap contained all 38 expected URLs
(two static routes plus 36 jobs), without operational paths or invented
lastModified values. Observed, sparse, reappeared, historical, filtered,
paginated, unknown and unavailable pages were checked for their actual metadata,
canonical and robots values. Dashboard route families inherit noindex/nofollow.
Controlled primary/sitemap API failures disclose no private diagnostics;
sitemap failure returns HTTP 500 without partial XML and the next request
recovers. Detail metadata/layout/page share one primary detail read; history
uses its separate read, and sitemap generation uses only the ID endpoint.

Final browser DOM checks confirmed one logical primary heading, useful content,
safe hostile title text, no JSON-LD/internal metadata leakage, server-side API
reads, no mobile overflow at 390px, clean console/error logs and zero axe
violations in observed, historical and mobile detail audits. Raw discovery HTML
can contain React's transient streaming fallback heading as well as final
content; the final DOM has one primary heading. In unconfigured mode public
pages remain usable, canonical/OG URLs are absent, robots disallows crawling,
and empty sitemap generation makes no API call.

Initial verification issues were corrected: a TypeScript test needed Open Graph
union narrowing; Ruff formatted a compact test; an unused test parameter was
removed. The isolated Turbopack build could not use a dependency symlink outside
its project root, so QA used a temporary local dependency copy. HTTP assertions
were adjusted for Next's normalized root URL and streaming fallback markup.
No production behavior was changed to accommodate those harness issues.

All temporary QA servers, the isolated database and the copied dependencies
were removed. Normal frontend/API services remain available; health, readiness,
public discovery, dashboard Jobs and the new sitemap API passed smoke checks.
The normal database's empty public listing state was preserved. Scope review
records 27 source/config/documentation files, with no migrations, dependency,
pipeline or persistence changes. QA logs and screenshots are retained under
`/tmp/openrole-task48-Oue3BuJr`.

**Task 48 implemented and verified.** No real production origin was supplied;
indexing remains disabled until `OPENROLE_SITE_URL` is configured at build and
startup and the frontend is rebuilt/restarted. The configured QA origin was
test-only. JobPosting remains explicitly deferred. At Task 48 completion,
Task 49 had not started; its later closure follows below.

## Task 49 integration verification and closure

**Phase 4 engineering verification: PASS — 2026-10-12.** All public workflows,
security boundaries, semantic copy, metadata/crawl policy, keyboard navigation,
desktop/tablet/mobile layouts and normal checks passed. Two durable acceptance
tests connect actual ingestion/change/absence/reappearance outcomes to all four
public read contracts, with a 120-job pagination/source-failure story.

Fresh results: backend 782 passed and two optional live-service tests skipped;
public API selection 75 passed; frontend 220 passed; Ruff, formatting, mypy,
lint and TypeScript passed. Clean configured/unconfigured production builds
succeeded with FastAPI unreachable. Actual browser/HTTP checks used an isolated
pipeline-backed dataset with 119 discoverable listings, safe controlled source
navigation, adversarial text/HTML, historical/return states and real API transport
timeouts. Twenty-seven recorded axe audits have no violations/incomplete results.

Task 49 changes only acceptance tests, plain-language discovery metadata and
documentation reconciliation. No dead dependency warranted removal, and no
schema, persistence, pipeline or new product capability was added. See
[phase-4-completion.md](phase-4-completion.md) for the complete checklist,
public architecture, tests, security review and prioritized limitations.

Production origin remains unconfigured, so indexing remains disabled. External
dashboard/admin access control and the inherited A→B→A history constraint remain
explicit follow-ups; no public deployment or exhaustive-history claim is made.
Developer understanding review remains pending. Phase 5 has not started.
