# Production configuration — blocker plan Task 1

This task hardens configuration before deployment. It does not provision a host,
database, bucket, credentials, proxy, HTTPS or production scheduler. Completing
it alone does not clear the deployment-readiness verdict.

## Environment files and separation

The backend continues to read the repository-root `.env` through Pydantic
Settings. `.env.production.example` is a **template**, not an automatically loaded
backend environment. On the production host, install its privately completed
contents as `/opt/openrole/.env`, or supply the same variables through the service
environment. Do not copy the development `.env` to production. Set
`APP_ENV=production`; frontend `NODE_ENV` does not set backend application mode.

The frontend template is `frontend/.env.production.example`. Next.js reads its
privately completed `.env.production` during production build/start. Remove
conflicting `.env.local` files from the production release. All current OpenRole
frontend configuration is server-only; database/R2 credentials belong only in the
backend environment. Templates contain blank secret values and no invented site
origin. Actual `.env`/`.env.*` files are ignored; `.env.example` and
`.env.*.example` remain trackable. The workspace still needs a valid Git repository
before tracking/history can be inspected.

Protect actual environment files with service-account ownership and restricted
permissions. Store production values privately, not in chat, templates or public
build variables. Use a distinct production database/storage and credentials;
syntax validation cannot establish whether an account is production-specific.

## Backend production rules

`Settings` applies the following checks only when `APP_ENV=production`:

| Setting | Requirement |
|---|---|
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
valid for the documented private, single-host PostgreSQL deployment.

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

`OPENROLE_API_BASE_URL` is the reachable private FastAPI URL. The template uses
the documented same-host localhost topology; adapt it if the services run on
different hosts. Browser requests do not need that URL or backend credentials.

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

The remaining tasks are deployment/proxy templates, private infrastructure
verification and the release gate. See the [Word deployment guide](OpenRole-Deployment-Guide.docx)
and [source automation](source-automation.md) for the existing deployment plan.
