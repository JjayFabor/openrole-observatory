# Production configuration — deployment preparation

This task hardens configuration before deployment. It does not provision a host,
database, bucket, credentials, proxy, HTTPS or production scheduler. Completing
it alone does not clear the deployment-readiness verdict.

## Environment files and separation

The backend continues to read the repository-root `.env` through Pydantic
Settings. `.env.production.example` is a **template**, not an automatically loaded
backend environment. For the selected Render deployment, enter the completed
values privately in the service environment. Local backend runs can still load
the root `.env`. Do not copy the development `.env` to production. Set
`APP_ENV=production`; frontend `NODE_ENV` does not set backend application mode.

The frontend template is `frontend/.env.production.example`. Next.js reads its
privately completed `.env.production` during production build/start. Remove
conflicting `.env.local` files from the production release. All current OpenRole
frontend configuration is server-only; database/R2 credentials belong only in the
backend environment. Templates contain blank secret values and no invented site
origin. Actual `.env`/`.env.*` files are ignored; `.env.example` and
`.env.*.example` remain trackable. The root Git repository tracks templates and
source files; completed environments, dependencies, raw data and build artifacts
are ignored.

Protect actual environment files with service-account ownership and restricted
permissions. Store production values privately, not in chat, templates or public
build variables. Use a distinct production database/storage and credentials;
syntax validation cannot establish whether an account is production-specific.

## Backend production rules

`Settings` applies the following checks only when `APP_ENV=production`:

| Setting | Requirement |
|---|---|
| `ADMIN_API_TOKEN` | Non-placeholder service bearer token of at least 32 characters; masked in settings representations |
| `DATABASE_URL` | `postgresql+asyncpg` URL with host, database, username and non-placeholder password; known development/default passwords are rejected |
| `OBJECT_STORAGE_BACKEND` | Explicitly supplied as `r2` or `filesystem`; the development default is insufficient |
| Filesystem `LOCAL_STORAGE_PATH` | Explicit absolute path on provisioned persistent storage, preferably outside release directories |
| R2 fields | Endpoint, access key, secret, bucket and region cannot be blank or common template placeholders |
| `R2_ENDPOINT_URL` | HTTPS Cloudflare R2 S3 hostname; no URL credentials, bucket path, query, fragment or non-HTTPS port |
| `R2_BUCKET_NAME` | The shipped `openrole-development` bucket is rejected in production |
| `R2_REGION` | `auto` or supported `us-east-1` alias; default `auto` is safe |

The database check rejects the known passwords `openrole`, `postgres`, `password`,
`development`, `test` and `change-me`, plus blank/template values. It is not a
password-strength assessment or proof of database connectivity. Localhost remains
valid for deliberate local/single-host deployments; Render requires a reachable
production database hostname.

R2 endpoint validation supports account and jurisdiction-specific hosts under
`.r2.cloudflarestorage.com`. Bucket region is separate from jurisdiction, which
belongs in the endpoint. See [Cloudflare's S3 API documentation](https://developers.cloudflare.com/r2/api/s3/api/).
The [jurisdiction endpoint documentation](https://developers.cloudflare.com/r2/reference/data-location/#using-jurisdictions-with-the-s3-api)
describes those endpoint variants.
Actual credential permissions, private-bucket status and immutable storage behavior
still require the deployment verification task.

An absolute filesystem path is a deliberate alternative for the approved
single-host beta. It does not prove that the path is durable, writable or backed
up. Provision and verify the directory before deployment. To choose it, set
`OBJECT_STORAGE_BACKEND=filesystem` and an absolute `LOCAL_STORAGE_PATH`; unused
blank R2 values do not invalidate filesystem settings.

Existing development/test defaults remain supported. Existing storage-factory
checks still apply when constructing storage, including outside production mode.
There is no database migration and no network call during settings validation.

## Frontend production rules

`OPENROLE_API_BASE_URL` is the actual Render API HTTPS origin. Vercel cannot
reach localhost on Render or its ordinary private network. Browser requests do
not need that URL or backend credentials. The production template contains an
explicit replacement hostname, which must be replaced before deployment.

`OPENROLE_ADMIN_API_TOKEN` matches Render's `ADMIN_API_TOKEN`. It is attached
only to administrative server-side requests. `OPENROLE_DASHBOARD_USERNAME` and
`OPENROLE_DASHBOARD_PASSWORD` supply the separate operator Basic credentials.
The password needs at least 32 characters; missing, partial or placeholder
credentials fail closed in production. Never put these values in `NEXT_PUBLIC_*`.

Set `OPENROLE_SITE_URL` to the actual HTTPS origin consistently at build and
startup. No domain has been selected, so the template leaves it blank. Existing
site validation rejects unsafe/non-origin/localhost production URLs; absent or
invalid configuration disables indexing, canonicals and sitemap advertisement
while retaining usable public pages. This behavior is unchanged.

`OPENROLE_DEFAULT_SOURCE_ID` remains optional and blank in the template. Select
an actual production source only after configuring and synchronizing it.

## Error handling and verification

Pydantic validates the completed settings before an engine or storage client is
constructed. Production failures identify variable names without echoing the
settings input. `DATABASE_URL` is excluded from settings representations; R2 keys
remain `SecretStr`. These protections do not redact deliberate `model_dump()`
output or `ValidationError.errors()` inputs: do not log configuration dumps or
serialize validation inputs into responses.

Tests cover both storage choices, omitted/relative/placeholder values, database
defaults, unsafe endpoint forms, error/repr redaction, environment-file precedence,
development/test compatibility and actual Git ignore semantics. Frontend tests
verify that its template stays server-only and preserves disabled indexing until
the origin is configured. Normal tests use synthetic credentials and no live R2.

Run PostgreSQL integration tests against a separate, empty, Alembic-migrated test
database using a test-only `DATABASE_URL` and `APP_ENV=test`. Existing API tests
assert empty initial lists and exact fixture totals; a populated development
database is not an interchangeable test target. This task does not change test
database selection or remove real development listings.

Deployment Task 2 adds the Render/Vercel templates and administrative guards.
Actual cloud infrastructure verification and the hosted release gate remain
pending. See the [Render/Vercel guide](deployment-render-vercel.md),
[Word deployment guide](OpenRole-Deployment-Guide.docx), and
[ADR 0004](adrs/0004-render-vercel-administrative-access.md).

## Task 2 local verification — 12 October 2026

- Full backend suite on an owned, separately migrated PostgreSQL test database:
  **901 passed, 2 optional live-service tests skipped**. The database was removed.
- Full frontend suite: **237 passed**; focused access tests also pass after final
  cleanup. Ruff, mypy, frontend lint/type checking and production build pass.
- Render Blueprint and Vercel configuration pass their published JSON schemas;
  the exact Corepack/frozen-lockfile install command succeeds locally.
- An isolated production frontend with a protected test-mode API verifies public
  access, authenticated dashboard reads, anonymous dashboard/API rejection,
  forged proxy bypass rejection, and HTTP 401 for the real compiled sync action
  posted anonymously to a public URL. Missing production frontend credentials
  give dashboard HTTP 503 while public pages remain accessible.
- Browser chunks contain no synthetic access credentials; the real local `.env`
  and existing 1,264 listings are preserved. The Word guide renders as six pages.

These are local checks. Hosted DB/R2 credentials, provider settings, HTTPS,
scheduled execution and backup/restore remain unverified. No cloud deployment
or public indexing approval is implied.
