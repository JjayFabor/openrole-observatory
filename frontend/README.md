# OpenRole frontend

`/` is the static public landing page. `/jobs` discovers currently observed
listings through the public FastAPI read API. Both use the public
header/main/footer layout. `/dashboard/*` retains the separate internal
operational layout and administrative FastAPI reads.

`/jobs/{jobId}` presents current listing facts, observation/lifecycle evidence,
safe descriptions and source links, and curated recent changes. Phase 4
engineering verification is PASS; see [the completion report](../docs/phase-4-completion.md)
for E2E evidence, deployment gates and remaining limitations. Developer review
remains pending. Configure the real site origin at build/startup before indexing;
dashboard/admin routes still require external protection.

`/dashboard` shows real system status, source synchronization health, and up to five recent pipeline runs. `/dashboard/jobs` explores current canonical jobs. `/dashboard/quarantine` inspects processing errors and record provenance. `/dashboard/sources` discovers source connections and opens operational source detail. Jobs and run detail routes inspect persisted histories and pipeline facts. Greenhouse remains the only supported provider.

## Run locally

Requires Node.js 22+ and pnpm 12.10.1. The public landing page
does not require FastAPI or PostgreSQL. For discovery or dashboard data, run
PostgreSQL and FastAPI using the root README instructions first.

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

Open http://localhost:3000 for the public landing page,
http://localhost:3000/jobs for discovery, or http://localhost:3000/dashboard for
internal operations. Configure `OPENROLE_API_BASE_URL` in your local environment
file for discovery and dashboard data (default
example: `http://localhost:8000`). Restart the frontend after changing it. Keep
`.env.local` private. The variable has no `NEXT_PUBLIC_` prefix because only
Next.js server code uses it.

The shell also works without FastAPI; checks show Unavailable. A backend readiness response that explicitly reports an unavailable database displays Not ready, while a failed readiness request leaves database status unconfirmed.

## Public shell and landing — Task 44

```text
/              public product explanation
/jobs          public job discovery
/jobs/[jobId]  current listing, observation evidence, safe description and recent changes
/dashboard/*   internal operations
```

The App Router `(public)` group shares a small header/main/footer shell without
changing the URLs. The root layout supplies HTML, body, global styles and brand
defaults; the dashboard keeps its own metadata and sidebar. Public navigation
links to home, Jobs and the landing page's How it works section. The landing
includes no API calls. Neither public page includes dashboard navigation,
internal identifiers or operator actions.

The landing explains direct configured employer ATS sources, observation
timestamps and preserved listing changes. "Observed" describes source evidence,
not confirmed hiring. Greenhouse is the current provider. The external
[source automation](../docs/source-automation.md) now triggers checks every six
hours; public copy uses actual observation timestamps without a monitoring SLA.
Task 47 presents curated recent listing changes;
full public version/lifecycle history remains deferred. The original Task 44 Jobs placeholder was replaced by
real discovery in Task 45.

The landing is a static server component. Shared typography,
tokens and Button styling match the dashboard, with a simpler, less dense public
layout. There are no added dependencies or animation. Landing metadata
includes title, description and Open Graph website fields. Task 48 adds explicit
site-origin/canonical/indexing policy. No custom OG images or invented host are
introduced.

The supplied OpenRole v4 SVGs live in `public/brand/` unchanged. The public
header uses the blue-accent wordmark, the navy footer uses its inverse, and the
dashboard sidebar and mobile drawer use the primary wordmark. The mobile
dashboard header uses the compact mark. `components/brand-logo.tsx` supplies
accessible image names and intrinsic dimensions; `app/icon.svg` supplies the
favicon through Next.js file-based metadata. Shared tokens in `app/globals.css`
use logo navy `#0F172A`, blue `#2563EB`, white and cool slate surfaces. Muted text
uses `#475569` for contrast; amber and red retain their warning/error meanings.

## Public job discovery — Task 45

`/jobs` is a dynamic server page. It calls only `GET /api/v1/public/jobs`, through
the shared server-only API client with uncached reads and a four-second timeout.
The backend owns discovery eligibility and ordering; the frontend preserves the
returned page rather than reclassifying or sorting listings.

| Public URL parameter | Behavior |
| --- | --- |
| `q` | Literal case-insensitive containment across title, company name or location text |
| `location` | Literal case-insensitive containment in location text |
| `workplace` | `remote`, `hybrid`, `onsite`; sent as `workplace_type` |
| `employment` | `full_time`, `part_time`, `contract`, `temporary`, `internship`, `volunteer`, `other`; sent as `employment_type` |
| `page` | One-based page; 25 results and `(page - 1) * 25` backend offset |

Filters intersect. Search does not include descriptions or external ATS IDs.
Location is unstructured text matching, not inferred city/country search. Source,
lifecycle, country and salary filters are not exposed. Unknown workplace and
employment data is not inferred; current Greenhouse mapping can leave these
fields unset, so filters may legitimately return no matches.

The labeled native GET form needs no custom filter JavaScript. Its omitted page
field resets pagination when submitted. The server normalizes whitespace, blanks,
invalid/repeated values and bounded text/page inputs before an API read. Pagination
retains filters; refresh and browser Back/Forward preserve committed URL state.
Backend totals determine pages, with excessive page requests redirected to the
last available page, or page one for zero results. Count/page reads can differ
under concurrent ingestion, so an in-range empty page remains a recoverable state.
The form disables autocomplete restoration so browser history returns controls
to the committed URL rather than retaining newer drafts. Its query key also
remounts controls when Next.js navigation changes committed filters.

Readable articles show title/company/location, known canonical type labels,
complete salary information and prominent **Last observed** UTC timestamps.
Salary formatting preserves exact decimal strings and omits incomplete values.
`Direct source · Greenhouse` describes source evidence rather than hiring
confirmation. Descriptions, internal identifiers, Apply/Save and recommendation
controls are absent. Source text renders escaped by React.

The API boundary maintains distinct public types, runtime validation and explicit
allowlist projections, including nested company/source fields. Failures retain
filters and display public-safe copy with a full-request retry. Empty datasets,
filter misses, changing pages and failures remain separate. Route loading uses
skeletons; unexpected errors use a public error boundary.

Selecting a listing opens the current public detail delivered by Task 46 below.
Jobs metadata describes actual discovery. Task 48 canonicalizes query variants to
`/jobs` when a site origin is configured.

## Public current job detail — Task 46

`/jobs/[jobId]` calls only `getPublicJob()` for `GET /api/v1/public/jobs/{jobId}`.
The existing public validator/projection remains the boundary; no admin detail,
versions or lifecycle-history reads occur. The async route layout, server page and dynamic
metadata use `getPublicJobDetail()`, a React `cache()` wrapper that shares the
read within one server request. `cache: "no-store"` and the four-second timeout
remain deliberate: a new document request reads current source evidence rather
than serving a long-lived cached lifecycle state. The shared client's AbortSignal
bypasses Next.js automatic fetch deduplication, so explicit request memoization
prevents duplicate metadata/page reads.

The header shows real title/company, location (or `Location not stated`), known
workplace/employment labels, and exact salary strings. Unlike compact discovery
cards, detail can show partial salary amounts with `currency unavailable` and/or
`period unavailable`; zero is preserved and missing units are never inferred.
**Last observed** uses `last_seen_at`, in UTC. **First observed** uses
`first_seen_at`, which does not establish the employer's posting date.

`Observed` is the stored backend lifecycle state. Tentative absence leaves it
Observed. `Not currently observed` shows a restrained notice, last observation
and optional `Absence confirmed` timestamp; this does not establish employer
closure. Observed jobs with `reappeared_at` get secondary reappearance context;
an old confirmation timestamp does not become a current absence warning. Known
historical and inactive-source jobs remain addressable; detail does not infer
discovery eligibility or promise continued monitoring from the Observed label.

`Direct source · Greenhouse` means employer ATS evidence, not an employer-verified
badge or hiring confirmation. Observed jobs offer **View original listing**;
not-observed jobs offer **Check original source**. The CTA uses only absolute,
credential-free HTTP(S), opens a new tab with `noopener noreferrer`, and has a
new-tab hint. Company domain is plain escaped text. The API requires a safe
source URL: malformed successful payloads show the unavailable state; the
component also guards the CTA defensively. There is no OpenRole application flow.

The shared `JobDescription` and `sanitizeJobDescription` path is used by both
public detail and the dashboard. The established `sanitize-html` policy removes
scripts, styles, handlers, images, forms and dangerous embedded content; it
retains safe div blocks, paragraphs, lists, emphasis, blockquotes and links. When
the description starts with entity-encoded markup, `entities.decodeHTML` decodes
exactly one outer layer **before** the allowlist sanitizer. Native HTML/plain text
keeps intentionally escaped tag examples; nothing is decoded after sanitization.
This display correction also applies to existing stored descriptions without
altering source bytes, canonical content hashes or historical versions. All source
heading levels become h3 under the page's Description h2. Description links have
the same credential-free HTTP(S)/new-tab security policy. Only sanitized HTML
reaches the HTML injection point. Empty/script-only content has a friendly public
fallback; plain multiline text preserves line breaks. Arbitrary provider styles,
classes and IDs cannot override the layout.

Metadata uses real title/company, known location/types and last-observed time.
Not-observed descriptions say `Historical listing`; titles never infer Closed or
Expired. The root template adds OpenRole once. Missing jobs call `notFound()`;
API failures have generic unavailable metadata and public retry copy. The page
is server-rendered, with only the unexpected-error reset boundary requiring
client interaction. Back to jobs goes to `/jobs`; browser Back retains discovery
URL filters. Loading skeletons contain no invented listing facts.

The detail files live under `(public)/(job-detail)/jobs/[jobId]`; the route group
adds no URL segment. It isolates detail from discovery's `/jobs/loading.tsx`.
The async detail layout resolves the bounded cached read before rendering its
children, so missing jobs produce an actual HTTP 404 before streaming begins,
including requests with an absent User-Agent. The feature not-found page sits at
the parent `jobs/not-found.tsx`, which catches failures from the child layout.
Initial detail documents wait for the lookup. `loading.tsx` supplies the route
skeleton; on client navigation its visibility depends on prefetch/loading-boundary
reuse and timing, so a brief skeleton is not promised on every navigation.
Task 48 supplies the current metadata, canonical and indexing policy. See [Task 46's production verification](../docs/phase-4.md#task-46-public-current-job-detail)
and [Next.js not-found behavior](https://nextjs.org/docs/app/api-reference/file-conventions/not-found).

Public versions, hashes, observation/run/snapshot/source/company IDs, lifecycle
counters and operational configuration are absent. Task 47 adds the curated recent-changes section below. Full public version and
lifecycle history remain excluded. Task 48 adds SEO policy below; JobPosting
structured data is explicitly deferred for missing factual publication data.

## Public recent listing changes — Task 47

Public detail now includes a secondary **Recent listing changes** section. A child
server component calls only `GET /api/v1/public/jobs/{jobId}/changes?limit=10`.
Its Suspense fallback keeps current listing content visible while changes load;
expected API/validation failures show `Change history is unavailable right now.`
A successful empty response says `No material listing changes recorded.` Metadata
and the primary cached existence/detail read do not depend on this request.
Both public reads keep their existing uncached, four-second timeout policy.

The endpoint returns complete transition groups in newest-observation order.
Distinct transitions sharing a timestamp remain separate. `limit` counts groups,
defaults to 10 and has a backend maximum of 50; each group contains at most nine
curated meanings. The UI requests ten groups, with no history pagination, invented
total or separate crawlable history pages. Stable internal UUID tie-breakers do
not appear in the response. UTC group labels use minute precision and describe
when OpenRole observed the changed state, not an exact employer action time.

Allowed fields are title, location text, city, region, country code, workplace,
employment, semantic Salary and description markers. Location facts remain
separate rather than inferred geography. Text renders escaped; known enums use
shared humanizers, null/blank values say `Not stated`, and unknown enum values
say `Unavailable`. Explicit Before/After labels convey direction without color
or icon dependence. Group and long-value layouts wrap on mobile.

Four low-level salary fields become one Salary change. Persisted events establish
that salary changed; narrow immutable version salary columns supply unchanged
context. Exact decimal strings and zero use the shared formatter. Partial amounts
qualify unavailable units. Unit-only records display `Amount not stated` plus
explicit currency/period facts, avoiding an uninformative null-to-null row.
Salary added/removed classification describes the presence of any structured
salary information, including units, rather than assuming amounts exist.

Description history contains only Added/Removed/Updated markers. Historical
HTML/bodies are neither fetched from PostgreSQL nor returned by the endpoint.
Source URL churn and generic canonical metadata are excluded before the group
limit is applied. No version, event, run, observation or snapshot IDs/numbers,
hashes, configuration or raw provider JSON reach the public response. Known
not-observed and inactive-source jobs retain recorded history.

The server-only client validates identity, bound, timestamps/order and typed
field-specific values, then explicitly projects allowed keys. Extra private
fields or historical description values cannot reach presentation. The frontend
never fetches versions, calls the admin history API or recalculates differences.

## Public SEO and crawl policy — Task 48

Set server-side `OPENROLE_SITE_URL` to the canonical origin only, for example the
actual HTTPS host you own, with no path/query/fragment/credentials. Set it for
both build and server startup; changing it requires a rebuild/restart because
the landing page is static. There is no default host. Production rejects HTTP,
localhost and common loopback origins. Explicit local HTTP origins are allowed
in development. Missing/invalid settings keep the site usable but disable public
indexing, omit canonical/OG URLs, disallow crawling, do not advertise a sitemap,
and make `/sitemap.xml` return an empty URL set without an API request.

With a configured origin:

| Route | Canonical | Robots metadata |
| --- | --- | --- |
| `/` | `/` | index, follow |
| `/jobs` | `/jobs` | index, follow |
| Meaningful `/jobs` filters or page > 1 | `/jobs` | noindex, follow |
| Observed meaningful `/jobs/{id}` | Stable self URL, without query parameters | index, follow |
| Not-observed `/jobs/{id}` | Stable self URL | noindex, follow |
| Unavailable detail | Omitted | noindex, nofollow |
| `/dashboard/*` | No public canonical/OG URL | noindex, nofollow inherited from layout |

Public metadata uses real listing title/company, optional known location/types
and last observation. Sparse fields are omitted naturally; company abbreviations
do not acquire doubled punctuation. Historical copy does not imply current
hiring. Open Graph uses `website`, the same factual title/description, configured
URL and `siteName: OpenRole`. No image, Twitter account, fabricated logo or
production host is invented. The existing request cache still shares one primary
read across layout/page/metadata, independently of recent changes.

`robots.txt` allows public pages and excludes dashboard/API paths, including base
and descendant paths. It advertises only the configured `/sitemap.xml`. Robots
is crawler guidance, not authentication; a crawler blocked by robots cannot read
page noindex. The dashboard retains its existing external access-control need.
See [Google's noindex limitations](https://developers.google.com/search/docs/crawling-indexing/block-indexing).

`/sitemap.xml` is dynamic and uncached. It calls the ID-only public endpoint
`GET /api/v1/public/jobs/sitemap?limit=1000&after=...`, never PostgreSQL directly.
All batches are walked in stable UUID order; it does not stop at 25 discovery
results. Eligible jobs match Task 43: observed, active source, one current version.
Historical/inactive-source pages stay addressable but are absent from the sitemap.
Reappearance restores eligibility when the source is active. Observed inactive-
source detail remains status-based indexable: the public detail contract does not
expose source-active configuration, so the frontend does not infer it.

Only root, default Jobs and eligible stable job URLs appear. `lastModified`,
priority and frequency are omitted rather than mapping source-observation times
to content edits. Batches reflect committed state at each read; concurrent sync
may change eligibility during a walk, and the next runtime generation rechecks it.
Failures reject the walk and yield HTTP 500 rather than a partial sitemap. A
single file is bounded to 50,000 URLs including the two static routes; exceeding
that bound fails explicitly and requires multiple-sitemap work rather than silent
truncation. Builds need no live backend because sitemap generation occurs at
request time. Robots/canonicals use configuration, not request Host headers.

**JobPosting JSON-LD: DEFERRED.** The public contract lacks reliable employer
`datePosted`; first observation is not publication. `validThrough`, employer-owned
identifier and applicant location restrictions are also unavailable. Description,
structured geography, employment and salary facts are optional; no location or
salary is parsed/inferred. Accordingly no JobPosting or structured salary is
emitted, even for complete salary records. No decorative site JSON-LD is added.
The field matrix and verification are recorded in [Task 48](../docs/phase-4.md#task-48-seo-and-crawlability).

## Overview source monitoring

Set optional server-only `OPENROLE_DEFAULT_SOURCE_ID` to the UUID of one existing source in `.env.local` or your process environment. The Sources explorer discovers existing sources; its detail page displays the UUID to use for this overview setting. Leave it blank to show the source-monitoring empty state. An invalid UUID or unknown source shows a safe source-section error without disrupting other sections.

Recent pipeline runs are a global list across all sources, regardless of the monitored source. The page states this scope and requests `limit=5&offset=0`; it does not derive sources from that list. Lifecycle totals are omitted because the backend does not expose aggregate job counts.

## Jobs explorer

`/dashboard/jobs` reads 25 current listings per page from `GET /api/v1/jobs`. It displays company/provider, canonical title and types, location, literal lifecycle status, observation timestamps, and current version number. The backend applies filtering and sorting (`last_seen_at` descending, job ID ascending); the frontend does not load the full dataset or make a detail request per row.

Search matches current title, location text, and external job ID with basic case-insensitive literal containment. Search and lifecycle filters are explicitly submitted with Apply filters or Enter. Committed state lives in URL parameters `q`, `status`, and `page`, so refresh and browser Back/Forward retain it. Filtering resets pagination to page one; pagination retains other filters.

Source discovery is available in the Sources explorer; this jobs page has no source selector. A shareable URL may include `source=<existing-source-uuid>` to scope the jobs read; this scope is displayed and retained when applying other filters or changing pages. Clear filters removes it. This is separate from the overview's optional monitoring-source environment variable. Invalid and repeated URL values use safe defaults; search is bounded to 200 characters and page offsets fit the backend integer range.

Observed and Not observed describe source evidence rather than employer intent. Dated absence/reappearance facts supplement the backend status without creating new statuses. Null or unknown canonical types show `—`, with no location-based inference. Timestamps use deterministic UTC formatting.

Empty datasets, filter misses, out-of-range pages, loading, and safe request failures have distinct states. The table scrolls inside a keyboard-focusable region on narrow screens. Job title links open `/dashboard/jobs/[jobId]`, backed by the current listing and independently fetched versions, changes, lifecycle history, and source information.

## Job detail and history

`/dashboard/jobs/[jobId]` displays current canonical content, conservative salary
formatting, source evidence, observation timestamps, and provenance. Descriptions
are sanitized server-side with an established HTML allowlist; diagnostics and
metadata remain escaped text. Salary decimals remain exact strings. Missing
canonical fields are not inferred.

Version, persisted field-change, lifecycle, and optional source reads settle
independently after the primary job read. A failed history section leaves current
content visible. Native disclosures make older content inspectable. Each history
uses bounded Previous/Next navigation; the backend exposes no total. Unknown jobs
show a specific 404. Content versions and source-presence events remain separate.

## Pipeline runs

`/dashboard/runs` displays 25 newest-first attempts per page. URL parameters
`status`, `source=<uuid>`, and `page` are shareable and refresh-safe. Status and
source predicates run in PostgreSQL before pagination. The list requests one
bounded lookahead row to determine Next; there is no invented total or last-page
number. Filters reset page one. A labeled source UUID field accepts any existing
source rather than a silently truncated source selector.

`/dashboard/runs/[runId]` reads the stored status, timestamps, six record/job
metrics, safe error code/summary, and source identity. Pending/running completion
is unavailable rather than zero duration. Numeric zero remains zero. Optional
source information may fail independently. Completed with errors describes
isolated record errors, while failed describes unsuccessful synchronization.
Quarantine links use actual run/source filters. RawSnapshot details and lifecycle
reconciliation counters are omitted because this read contract does not expose
those facts. Unknown runs show a specific 404. No polling or retry action is added.

## Quarantine inspection

`/dashboard/quarantine` reads 25 records per page from `GET /api/v1/quarantine`, newest first (`created_at` and ID descending). Status/category controls submit URL state explicitly. Parameters `status`, `category`, `page`, optional `source=<uuid>`, and `run=<uuid>` survive pagination, refresh, and Back/Forward; applying controls resets to page one while preserving source/run scopes. Clear filters removes all scopes. There is no source/run discovery dropdown. The category selector reflects five actual backend writer categories and preserves a valid unknown category supplied through a URL.

The list separates record status, source/company, recoverable external ID, diagnostic category/code/message, raw locator, run, and UTC creation time. A missing identity is identified without asserting that it caused the error. `total` comes from the same backend filters rather than counting the page. Empty datasets, filter misses, out-of-range pages, loading, and backend errors are distinct.

`/dashboard/quarantine/[recordId]` fetches one record with its structured error details, identity, resolution timestamp, and provenance IDs. Invalid UUIDs and missing records show a record-specific not-found state. Messages and JSON render as escaped text, with bounded/wrapping scrollable JSON and a native disclosure for large details. Nested zero, false, null, arrays, and objects remain intact. The frontend receives no malformed raw body, source configuration, object-storage credentials, keys, or signed URLs.

Recoverable identity can contribute presence evidence; missing identity can prevent safe absence reconciliation. These notes do not calculate or claim an actual run-safety decision. A quarantined record does not establish that the entire run failed. Status is inspection-only: there are no resolve/retry/replay/edit/delete actions.

Quarantine links to persisted `/dashboard/runs/[runId]`, preserving source navigation context. Run detail links back to source/run-filtered quarantine records. The overview's source card links its latest positive quarantine count to the same run filter.

## Sources explorer and detail

`/dashboard/sources` reads 25 source connections per page from `GET /api/v1/sources`, ordered by company name and source ID. The All sources/Active/Inactive control submits the `active` URL parameter; `page` preserves pagination across refresh and Back/Forward. Changing the filter resets page one. Totals come from the same backend filter. Empty configuration, filter misses, out-of-range pages, loading, and safe failures have distinct states.

Rows show company/provider, configured active state, attempted and successful synchronization timestamps, latest run status, and real fetched/quarantined counts. Active configuration and run outcome are separate facts. Never synchronized means both synchronization timestamps are null; missing dates and metrics display `—`. No job totals or freshness-health thresholds are invented.

`/dashboard/sources/[sourceId]` first reads the safe source and company projection. Invalid IDs and missing sources show a source-specific not-found page. It then requests up to five source-scoped runs and five source-scoped quarantine records concurrently. Either related request can fail without hiding the source or the other history. Response source IDs are checked before displaying source history. A failed latest attempt remains visible beside an older successful synchronization.

Detail links to source-filtered jobs and quarantine. Its Runs link opens the real explorer filtered by source. Run Detail reads the persisted run and uses its authoritative source identifier for return navigation. Jobs, quarantine, and the overview source card link back to source detail.

Company and diagnostic text render as escaped text. Careers links accept only absolute HTTP(S) URLs without embedded credentials. API projections omit source configuration and account keys. Source configuration remains inspection-only: no create, edit, enable, disable, test, schedule, or delete controls are provided. Existing active sources support the manual synchronization described below.

## Manual source synchronization

Source detail provides one **Sync now** action for an existing active source. Inactive sources show a disabled button with an explanation. The button calls a Next.js Server Action, which sends one body-free `POST /api/v1/sources/{id}/sync` to the existing FastAPI endpoint. API configuration remains private; built-in Server Action origin protections remain enabled. There is no browser-to-FastAPI request, retry, polling, queue, or progress percentage.

The synchronous mutation has a separate five-minute timeout; read requests retain their four-second timeout. A synchronous local guard and disabled **Synchronizing…** state prevent duplicate clicks while the request or persisted-state refresh is pending. The backend independently rejects an already-running source synchronization with a conflict response.

Completed feedback displays actual fetched/new/changed/unchanged metrics. Completed with errors displays its quarantined count, a run-filtered quarantine link, and an amber outcome. A defensive failed-run response displays failure. Available run links open persisted Run Detail. Error feedback uses documented status/code pairs and trusted frontend text, never arbitrary backend messages or caught exception details. HTTP error envelopes provide no run ID, so their feedback cannot invent a failed-run link.

Terminal HTTP responses invalidate source detail/list, overview, jobs, quarantine, and runs views and refresh persisted source facts. Feedback remains in the mounted client component; results never optimistically overwrite the source or latest run. If a response is lost to a transport failure or client timeout, the page retains its existing facts and inline error because the outcome may be unknown. Refresh the page before retrying an unknown result. Setup and invalid-identifier errors use specific safe guidance.

## Validate and build

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm start
```

The build does not need a running backend. Overview, jobs, quarantine, and source reads happen at request time with `cache: "no-store"`, each with a four-second timeout. A production server needs the same environment variables as development. Refresh the page to fetch current data; there is no polling.

## Structure and boundaries

- `app/dashboard/layout.tsx` renders the persistent sidebar, header, and main content. `loading.tsx` and `error.tsx` replace the page content while the shell stays available.
- `app/dashboard/page.tsx` is a server component. `lib/api/overview.ts` starts independent system, source, and run reads concurrently and settles them separately. One failed endpoint leaves successful sections visible. `system.ts`, `sources.ts`, and `pipeline-runs.ts` validate only the consumed backend contracts through the shared `lib/api/client.ts` and `validation.ts`.
- Presentation components receive typed data. UTC absolute timestamps and relative freshness use one server-render reference time, so they do not change during hydration. Duration is calculated from run timestamps; pending/running labels use backend status. No lifecycle rules or freshness-health thresholds are calculated in the frontend.
- Recent runs use a semantic table on desktop and compact lists on smaller screens. Quarantined counts and partial-success/failure statuses remain visible in both. Backend error codes and documented safe summaries render as escaped text; caught exceptions are never displayed.
- Client components handle active navigation, the accessible mobile drawer, error-boundary retry, and the guarded source synchronization control. The API modules import `server-only` to prevent accidental browser use.
- `components/ui/` contains the small shadcn-compatible Button, Badge, Separator, Skeleton, and Sheet base. `components.json` configures aliases and Tailwind CSS variables. Drawer behavior uses Radix Dialog for keyboard/focus handling.
- The jobs, quarantine, and sources server pages validate URL state in their feature query modules and call server-only API functions. Only filter draft inputs/navigation are client-side; they do not call FastAPI from the browser. Job and run details use primary resource reads with independent secondary information. Source detail composes primary and independent related reads in `lib/api/source-detail.ts`.
- Next.js talks to FastAPI, which owns PostgreSQL access and domain behavior. There are no duplicate API routes, database connections, or lifecycle calculations in the frontend. Initial calls are server-to-server, so they do not need browser CORS.

Tests use Node's test runner and `tsx`, with mocked fetch responses and the React server condition so `server-only` modules can be tested. Only consumed response types are maintained manually; OpenAPI client generation may be considered when the API surface grows.

The quarantine and source component safety tests render actual components in a subprocess using ReactDOMServer's normal React export, verifying that source/debug markup remains escaped text and that provenance/identity notes and the overview run-filter link remain factual. Source tests also verify safe careers links, source navigation, never-synchronized facts, and configured active state beside a failed latest run.

ESLint 9.39.5 is pinned because the plugins bundled with the current Next.js ESLint configuration declare support through ESLint 9. Installation reports its upstream deprecation; ESLint 10 should be adopted when those plugins support it. `pnpm-workspace.yaml` allows only the esbuild and unrs-resolver dependency build scripts needed by the toolchain.

This foundation has no authentication. Keep it local or behind existing external access controls when deploying internally.

## Render/Vercel deployment preparation

Import this repository into Vercel with root directory `frontend` and Node.js
22.x. `vercel.json` uses Corepack and the pinned pnpm version with a frozen
lockfile; set `ENABLE_EXPERIMENTAL_COREPACK=1` for builds. Supply production
variables using `.env.production.example` as a checklist; use the Render API's
HTTPS origin, not localhost. Backend database/R2 secrets remain on Render.

Production `/dashboard/*` is protected by an HTTP Basic username/password prompt.
The layout, administrative API client and manual sync Server Action independently
check authorization. `OPENROLE_ADMIN_API_TOKEN` matches Render's separate bearer
token and stays server-only. Missing dashboard credentials block access in
production; local development without configured credentials remains accessible.
Public routes remain public and noindex until the canonical site origin is set.

Source Detail requests a 300-second platform function duration for manual sync;
verify your compute settings permit it. Timed-out ingestion may still be running
on Render; inspect persisted runs before retrying. See the complete
[deployment guide](../docs/deployment-render-vercel.md) and
[ADR 0004](../docs/adrs/0004-render-vercel-administrative-access.md).
