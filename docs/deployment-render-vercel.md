# OpenRole deployment: Render API and Vercel frontend

This is the selected deployment topology. No Ubuntu VPS, Nginx or systemd is
required for production. Configuration and local verification are prepared;
actual cloud provisioning, production infrastructure checks, backup/restore and
the hosted release gate are still pending. No service has been deployed by this task.

## 1. Prepare the accounts and production resources

Use the existing GitHub repository `JjayFabor/openrole-observatory`, branch `main`.
Authorize Render and Vercel to read that repository. You also need production
PostgreSQL and a private Cloudflare R2 bucket. Neon is the originally planned
database provider; Render Postgres is another supported deployment option. This
template does not provision a database or select a provider for you.

Keep the production DB and bucket separate from development. Enable provider
backups with retention and test a restore to a separate database before launch.
R2 credentials must permit the existing application's reads/writes for that
private bucket. Do not enable public bucket access. Database/R2 credentials
belong only on Render, never on Vercel or in GitHub source files.

Render's Blueprint uses paid `0.5c-512mb` API/cron compute because pre-deploy
migrations require a paid API service. Review current pricing and region before
creating services. There is no cloud purchase/provisioning in the repository.
See [Render's Blueprint reference](https://render.com/docs/blueprint-spec) and
[pre-deploy behavior](https://render.com/docs/deploys#pre-deploy-command).

## 2. Prepare backend environment values privately

Use `.env.production.example` as a variable checklist, entering values in
Render's Environment settings. Do not upload the development `.env` or commit
a completed production file. Service variables override dotenv defaults.

| Variable | Production value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Direct PostgreSQL connection URL using `postgresql+asyncpg://` |
| `ADMIN_API_TOKEN` | At least 32 random characters; Blueprint can generate it |
| `OBJECT_STORAGE_BACKEND` | `r2` |
| `R2_ENDPOINT_URL` | Your account's HTTPS R2 S3 endpoint |
| `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Private bucket credentials |
| `R2_BUCKET_NAME` | The distinct production bucket name |
| `R2_REGION` | `auto` |
| `JOB_ABSENCE_CONFIRMATION_RUNS` | `2` |

Use a direct DB connection, rather than a transaction-pooling URL: the existing
pipeline uses session-level PostgreSQL advisory locks. When adapting a provider's
connection string for SQLAlchemy/asyncpg, change the scheme to
`postgresql+asyncpg` and use the asyncpg `ssl` argument, not libpq's `sslmode` or
`channel_binding` query parameters. For an external hosted DB, a typical form is:

```text
postgresql+asyncpg://USER:ENCODED_PASSWORD@HOST/DATABASE?ssl=require
```

Percent-encode reserved characters in credentials. `ssl=require` requires TLS;
certificate verification is a separate client/provider setting. Where supported
with the proper CA trust, use `ssl=verify-full` for certificate/hostname checks.
For Render Postgres in the same workspace/region, use its internal URL; its
private hostname is reachable by both API and cron, but not by Vercel.
Verify the actual TLS/connection setup in the infrastructure-check task.
See [Render Postgres connections](https://render.com/docs/postgresql-creating-connecting)
and [asyncpg SSL parameters](https://magicstack.github.io/asyncpg/current/api/index.html).

The API token and dashboard password are separate credentials. Generate each
privately, for example with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
Never paste the resulting credentials into chat or commit them.

## 3. Create the Render API first

Create a **Web Service** connected to the GitHub repository and `main`. Use:

| Setting | Value |
| --- | --- |
| Root directory | `backend` |
| Runtime | Python |
| Python version | `.python-version` selects the latest supported 3.12 patch |
| `UV_VERSION` | `0.12.23`, matching local tooling |
| Build command | `uv sync --frozen --no-dev` |
| Pre-deploy command | `uv run --no-sync alembic upgrade head` |
| Start command | `uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/ready` |
| Auto-deploy | Disabled during preparation |

Supply all backend values before the first deploy. The pre-deploy step applies
the existing Alembic chain; it does not seed fixtures or company sources. The
API starts only after that command succeeds. Confirm `/health` is HTTP 200 and
`/ready` is HTTP 200. Save the actual `https://...onrender.com` API origin.

`render.yaml` records both Render services and their environment references.
You may use a Blueprint after reviewing its plans/region and secret prompts.
For the first rollout, creating the API first and the cron job after readiness
avoids scheduling discovery before the initial database migration completes.
`sync: false` values are prompted on initial Blueprint creation only; later
secret changes are made privately in the service settings. Cron's references
refresh on Blueprint sync, so confirm both services' values after rotations.

## 4. Create the Vercel project

Import the same GitHub repository, selecting **Root Directory: `frontend`** and
the Next.js framework. Use **Node.js 22.x**. Set `ENABLE_EXPERIMENTAL_COREPACK=1`
for builds; `frontend/vercel.json` invokes Corepack so the repository's pinned
pnpm version is used instead of Vercel's inferred default. The install command
uses the frozen lockfile and the build command is `pnpm build`.
See [Vercel package managers](https://vercel.com/docs/package-managers).

Enter the following **Production** environment values before deploying:

| Variable | Value |
| --- | --- |
| `OPENROLE_API_BASE_URL` | Actual Render API HTTPS origin, without a trailing endpoint path |
| `OPENROLE_ADMIN_API_TOKEN` | The same value as Render's `ADMIN_API_TOKEN` |
| `OPENROLE_DASHBOARD_USERNAME` | Your single operator username, without `:` |
| `OPENROLE_DASHBOARD_PASSWORD` | A separate randomly generated password, at least 32 characters |
| `OPENROLE_SITE_URL` | Leave blank until your actual canonical HTTPS origin is chosen |
| `OPENROLE_DEFAULT_SOURCE_ID` | Optional real source UUID; leave blank initially |

Do not use `localhost` or Render's internal hostname for the Vercel API URL.
Never prefix secrets with `NEXT_PUBLIC_`. Vercel supplies production `NODE_ENV`.
Keep production admin credentials out of preview deployments by default; those
dashboards fail closed until deliberately configured for a separate test environment.

The source-detail route requests a 300-second function duration for the existing
synchronous manual sync action. Confirm your Vercel compute settings support it.
The API client's five-minute timeout does not extend a platform limit. If a
request times out, inspect persisted runs before retrying: ingestion may still
be running on Render. No queue or background job API is added.

`/`, `/jobs`, listing detail, robots and sitemap remain public. `/dashboard/*`
prompts for the operator's Basic credentials. The proxy also challenges Server
Action requests posted to public URLs, since the sole action is administrative.
The Server Action and administrative
reads independently check the request credentials; frontend hiding is insufficient.
FastAPI administrative routes require the separate bearer token even through the
direct Render URL. Production `/docs`, `/redoc` and `/openapi.json` return 404.
See [ADR 0004](adrs/0004-render-vercel-administrative-access.md).

Project-wide Vercel Deployment Protection may be useful for previews, but it is
not a dashboard-only rule. Do not gate the entire production public site when
configuring that feature. Frontend reads are server-to-server; browser CORS is
not required and is not administrative access control.

## 5. Configure automatic source discovery and synchronization

After migrations and `/ready` pass, create a Render **Cron Job** using the same
repository, branch, `backend` root, Python version, frozen build command and
backend environment values. Use:

```text
Schedule (UTC): 0 4,10,16,22 * * *
Command: uv run --no-sync python -m app.cli.automate_greenhouse
```

This is 00:00/06:00/12:00/18:00 Asia/Manila. It gradually admits up to 25 verified
new Greenhouse boards per cycle, then syncs all active configured sources through
the existing pipeline. It does not guarantee discovery of every company board.
The CLI creates real sources; do not run `seed_dev` against production.

The API and cron must use the same production DB and private R2 bucket. Render
cron jobs cannot access persistent disks, which is why local filesystem Bronze
storage is unsuitable for this deployment. The database locks handle overlapping
cron/manual sync attempts; scheduling frequency is not a source freshness SLA.

Trigger an initial run only when no cron cycle is active: Render's **Trigger Run**
cancels an active cron run. Normal scheduled invocations wait for an existing
run to finish. Review cycle JSON, per-source runs and quarantines. Exit 1 may
include isolated source/record failures; do not interpret those as removals.
See [Render cron behavior](https://render.com/docs/cronjobs) and
[source automation](source-automation.md).

## 6. Verify before launch

From an anonymous browser/request, check that public landing/jobs work, dashboard
GET and POST requests are challenged, and direct Render administrative reads and
sync POSTs return 401. Verify the operator can load the dashboard and sync a real
source; repeated unchanged sync must not create a new job version. Inspect the
raw snapshot in the private R2 bucket and its persisted lineage.

Also verify HTTPS, a production-specific migrated database, readiness failures,
scheduled execution, backup retention and a tested restore. These are hosted
checks; local tests and schemas do not establish that they passed.

Set `OPENROLE_SITE_URL` to the final HTTPS public origin when chosen and redeploy.
Until then, existing public pages remain noindex, with no canonical URLs or
sitemap advertisement. Do not invent a domain or publish JobPosting claims.

## 7. Updates and recovery

Keep deployments manual during the release gate. Before schema changes, suspend
future cron scheduling and wait for an active cycle to finish; avoid manual
Trigger Run/cancellation during ingestion. Back up PostgreSQL and preserve R2
objects independently of application releases. Deploy the API migration/code,
verify readiness, deploy matching cron/frontend code, then resume scheduling.

An application rollback does not roll back a database schema automatically.
Inspect migration compatibility and retained data before any downgrade. Interrupted
`running` pipeline records still need operator investigation; this task does not
add automatic recovery. Use provider logs to inspect failures without logging
authorization headers, URLs containing database passwords or environment dumps.
