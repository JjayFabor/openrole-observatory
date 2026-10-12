# OpenRole Observatory — Phase 1 Completion Report

Date: 2026-10-06

## Summary

**Phase 1 status: PASS.**

OpenRole now has a coherent Greenhouse ingestion pipeline that preserves exact
source bytes, validates provider records, maps valid records into a canonical
job model, detects new/unchanged/changed content, retains immutable history,
quarantines malformed child records, and exposes operational state through a CLI
and restricted administrative API.

No Phase 2 behavior was introduced.

## Architecture delivered

```text
CLI / restricted admin API
        ↓
SourceSyncService
        ↓
PostgreSQL per-source advisory lock
        ↓
PipelineRun → GreenhouseClient
        ↓
exact bytes → ObjectStorage (filesystem / R2)
        ↓
RawSnapshot → validation → SourceObservation
        ↓
CanonicalJobInput → material SHA-256
        ↓
NEW              UNCHANGED             CHANGED
Job + v1         freshness only        close old + create new
        └──────────────┬───────────────────┘
                       ↓
       quarantine invalid child records
                       ↓
       completed / completed_with_errors / failed
```

External HTTP and object-storage I/O occur outside database transactions.
Transactions remain short around run state, snapshot metadata, observations,
job/version mutations, and quarantine persistence.

## Component audit

`PASS` under Understood means the implementation is explicit and documented;
the developer should confirm personal understanding using the final review
questions.

| Component | Implemented | Tested | Documented | Understood |
|---|---:|---:|---:|---:|
| FastAPI foundation | PASS | PASS | PASS | REVIEW |
| PostgreSQL connection | PASS | PASS | PASS | REVIEW |
| Alembic | PASS | PASS | PASS | REVIEW |
| Company | PASS | PASS | PASS | REVIEW |
| SourceConnection | PASS | PASS | PASS | REVIEW |
| PipelineRun | PASS | PASS | PASS | REVIEW |
| RawSnapshot | PASS | PASS | PASS | REVIEW |
| ObjectStorage contract | PASS | PASS | PASS | REVIEW |
| Filesystem storage | PASS | PASS | PASS | REVIEW |
| R2 storage | PASS | PASS | PASS | REVIEW |
| Greenhouse fixtures and schemas | PASS | PASS | PASS | REVIEW |
| CanonicalJobInput and mapper | PASS | PASS | PASS | REVIEW |
| Canonical serialization and hash | PASS | PASS | PASS | REVIEW |
| Job and JobVersion | PASS | PASS | PASS | REVIEW |
| SourceObservation | PASS | PASS | PASS | REVIEW |
| QuarantineRecord | PASS | PASS | PASS | REVIEW |
| GreenhouseClient | PASS | PASS | PASS | REVIEW |
| PipelineRunService | PASS | PASS | PASS | REVIEW |
| Raw acquisition | PASS | PASS | PASS | REVIEW |
| Source-record processing | PASS | PASS | PASS | REVIEW |
| New job path | PASS | PASS | PASS | REVIEW |
| Unchanged job path | PASS | PASS | PASS | REVIEW |
| Changed job path | PASS | PASS | PASS | REVIEW |
| Record orchestration | PASS | PASS | PASS | REVIEW |
| SourceSyncService | PASS | PASS | PASS | REVIEW |
| Seed and sync CLI | PASS | PASS | PASS | REVIEW |
| Administrative API | PASS | PASS | PASS | REVIEW |

The R2 adapter passes automated contract/unit tests. Its live external smoke test
was not run because credentials were unavailable; this is allowed by the Phase 1
completion gate.

## Verification results

Clean bootstrap and migrations:

```text
docker compose down -v                         PASS
docker compose up -d postgres                  PASS (healthy)
uv run alembic upgrade head                    PASS
uv run alembic current                         3e7f3cd24003 (head)
uv run alembic history                         PASS (one linear 5-revision chain)
uv run alembic downgrade base                  PASS
uv run alembic upgrade head                    PASS
```

Final automated checks, run after live data existed in PostgreSQL:

```text
uv run pytest                                  314 passed, 2 skipped
uv run ruff check .                            PASS
uv run ruff format --check .                   PASS (123 files)
uv run mypy                                    PASS (117 source files)
```

The skipped tests were the intentionally gated live Greenhouse and R2 tests.
The Greenhouse test was then enabled separately and passed. The R2 test remained
disabled because credentials were unavailable.

One non-failing warning remains: the installed Starlette `TestClient` emits a
deprecation warning about its current `httpx` integration.

## Authoritative fixture acceptance scenario

The PostgreSQL/filesystem acceptance test uses mocked HTTP and saved fixtures:

| Scenario | Status | Fetched | Valid | Quarantined | New | Changed | Unchanged |
|---|---|---:|---:|---:|---:|---:|---:|
| First `jobs_v1.json` | completed | 4 | 4 | 0 | 4 | 0 | 0 |
| Identical second sync | completed | 4 | 4 | 0 | 0 | 0 | 4 |
| `jobs_v2.json` | completed | 4 | 4 | 0 | 0 | 2 | 2 |
| Invalid child fixture | completed_with_errors | 3 | 2 | 1 | 2 | 0 | 0 |
| Empty source | completed | 0 | 0 | 0 | 0 | 0 | 0 |

After the three valid-version scenarios, the database contains four Jobs,
six JobVersions, twelve SourceObservations, and three RawSnapshots. The repeated
sync grows observations but not jobs or versions.

## Lineage and replayability

The acceptance test joins and verifies this complete chain:

```text
JobVersion
→ SourceObservation
→ RawSnapshot
→ PipelineRun
→ SourceConnection
→ Company
```

It then retrieves the Bronze bytes through `ObjectStorage`, applies the
observation's `jobs[index]` locator, and verifies the original Greenhouse job ID.
The quarantine test performs the equivalent recovery for a malformed record.

Stored Bronze data therefore supports a future deliberate replay/backfill
mechanism without calling Greenhouse again. Replaying the exact already-processed
PipelineRun blindly is not supported because run-scoped uniqueness constraints
correctly reject duplicate observations.

## Idempotency, history, and freshness

- Stable identity is `(source_connection_id, external_job_id)`.
- Canonical material content is serialized deterministically and hashed.
- An equal canonical hash advances `last_seen_at`, creates a new observation,
  and creates neither a Job nor a JobVersion.
- A changed canonical hash closes the previous current version and creates one
  new current version in the same transaction.
- Version 1 retains its original content and SourceObservation reference;
  `v1.effective_to == v2.effective_from`, while Version 2 has no `effective_to`.
- Stale observations cannot move `last_seen_at` backward.
- Raw-response hashes and canonical-content hashes remain separate because they
  protect different representations.

## Quarantine behavior

`jobs_invalid_record.json` contains three child records. Two valid jobs persist;
the child at `jobs[1]` has no Greenhouse ID and becomes one open
`QuarantineRecord` with category `record_validation_failed`, no external ID, and
source-index details. The raw locator recovers the malformed object from the
stored Bronze response. The run finishes as `completed_with_errors`, so valid
data is not discarded.

## Failure and locking verification

Automated failure injection proves:

- Greenhouse timeout: failed run, `SOURCE_REQUEST_TIMEOUT`, no RawSnapshot;
- storage write failure: failed run, `RAW_STORAGE_FAILED`, no RawSnapshot;
- storage success plus snapshot-row failure: failed run,
  `DATABASE_WRITE_FAILED`, and the immutable raw object is documented as an
  orphan;
- raw-byte hash/length mismatch: failed run, `SOURCE_RESPONSE_INVALID`, no
  canonical processing;
- invalid top-level Greenhouse response: failed run, no fake quarantine row;
- unexpected internal error: failed run, `PIPELINE_INTERNAL_ERROR`, sanitized
  external message and logged traceback.

The PostgreSQL advisory lock prevents concurrent runs for the same
SourceConnection, does not block a different SourceConnection, and is shown to
be reacquirable after success, partial success, expected failure, and unexpected
exception.

## Actual PostgreSQL schema review

`psql \d` was run against all eight Phase 1 tables. The deployed schema has:

- UUID primary keys and named foreign keys with restrictive deletion;
- unique source identity and per-run observation identity;
- a partial unique index allowing only one current JobVersion per Job;
- uniqueness for version number, content hash, and version lineage;
- non-negative metric, record-count, byte-length, salary, and version checks;
- ordered job freshness and version effective-time checks;
- JSONB configuration/metadata/detail columns;
- timezone-aware timestamps; and
- SHA-256 shape constraints where hashes are stored.

## External and manual smoke tests

### Greenhouse — PASS

The gated live client test made one request to a public Greenhouse board and
verified HTTP 200, non-empty exact response bytes, timezone-aware retrieval time,
and successful top-level/child validation.

### Filesystem full sync — PASS

The real seed command created one development source and returned the same source
on a second invocation. The live CLI synchronization produced:

```text
status=completed
fetched=720
valid=720
quarantined=0
new=720
changed=0
unchanged=0
```

The resulting Bronze object was 5,577,545 bytes. Its on-disk SHA-256 matched the
`RawSnapshot.content_hash` in PostgreSQL. A second live sync through the API
reported 720 unchanged records. The database then contained 720 Jobs,
720 JobVersions, 1,440 SourceObservations, two RawSnapshots, and two PipelineRuns.

### FastAPI and CLI — PASS

The running application returned HTTP 200 for `/health`, `/ready`, the
pipeline-run list, pipeline-run detail, and the source-sync POST. A CLI request
for a nonexistent source exited with status 1 and stable code
`SOURCE_CONNECTION_NOT_FOUND`.

### R2 — NOT RUN — credentials unavailable

The adapter remains covered by normal tests for put/get/exists, immutable-write
protection, provider configuration, safe error translation, and credential
redaction. The gated live test also deletes only its unique test object.

## Performance sanity and query review

A synthetic 100-record end-to-end test completed successfully with exactly 100
jobs, versions, and observations. The live 720-record source also completed
without timeouts or duplicate outcomes. Processing is intentionally sequential
and currently performs per-record persistence work; this is acceptable for
Phase 1 but is recorded as scaling debt rather than prematurely optimized.

## Configuration, dependencies, and security

- `.env.example` contains every current setting and placeholder-only R2 values.
- Filesystem mode does not require R2 credentials; R2 mode validates all required
  values and reports missing variable names without exposing secrets.
- `.env`, local Bronze data, caches, coverage output, and common IDE state are
  ignored.
- Four previously tracked Python bytecode artifacts were removed.
- No real credentials or secret identifiers were found in tracked source.
- Logs retain operational IDs and metrics but do not emit raw payloads,
  descriptions, authorization headers, database URLs, or R2 secrets.
- Broad exception handlers either translate/re-raise, finalize failure, log a
  traceback, or deliberately fall through from one typed job path to the next;
  no `except Exception: pass` pattern exists.
- The Greenhouse client uses explicit connect/read timeouts, bounded retries,
  capped backoff, retryable status classification, and one shared async client
  per runtime service context.
- No CORS policy or debug mode is enabled.
- Every runtime and development dependency in `pyproject.toml` has an active
  Phase 1 use; none were removed.

The administrative API has no application authentication. It must remain behind
a private network, reverse-proxy access restriction, platform authentication, or
equivalent external control.

## Documentation changes

- Added `product-spec.md` as the product-scope source of truth.
- Updated the README with the real migration chain, seed syntax, Phase 1 API,
  fixture name, and complete lineage.
- Reconciled `phase-1.md` with the delivered module layout, CLI commands,
  ObjectStorage terminology, fixture name, and actual API scope.
- Removed task-number coupling from architecture/data-model explanations.
- Added this completion report.

## Cleanup performed

- Removed the unused FastAPI database-session dependency.
- Added one central ORM model registry, replacing duplicated registration lists
  and fixing fresh-process seed execution.
- Added a subprocess regression test for mapper registration.
- Made database count assertions relative to a per-test baseline so the suite
  remains valid with existing developer data.
- Removed tracked Python bytecode and expanded ignore rules.
- Added the previously missing idempotent development seed command.
- Removed the reproducible live-smoke Bronze objects and rebuilt PostgreSQL as
  an empty, healthy database migrated to the Phase 1 head revision.

## Known limitations

- Greenhouse is the only source provider.
- Synchronization is synchronous and manually triggered; no scheduler or worker
  queue is included.
- The administrative API has no application authentication.
- Removal and reappearance detection are not implemented.
- There is no public job/search/history API or frontend.
- There is no replay CLI; Bronze data only establishes the evidence needed for a
  future deliberate replay/backfill workflow.
- Snapshot metadata persistence can leave an immutable orphan object after a
  successful upload and failed database insert.
- Live R2 behavior was not exercised during closure because credentials were
  unavailable.

## Concrete technical debt

- **High before public exposure:** add application authentication or guarantee an
  external access-control boundary for administrative routes.
- **Medium:** add orphan-object reconciliation for storage-success/database-fail
  cases.
- **Medium:** profile and batch the sequential per-record database path when
  source volume demonstrates a real bottleneck.
- **Low:** replace Starlette `TestClient` usage when the supported FastAPI testing
  stack removes the current deprecation warning.
- **Low:** consider renaming the provider-neutral database column
  `raw_snapshots.r2_object_key` to `object_key` in a future schema migration.

## Phase 2 readiness and recommendation

Phase 1 is ready to support Phase 2. The recommended next direction is the
documented historical-change lifecycle: detect disappearance and reappearance,
record field-level diffs/events, and expose those results through a small
read-only history API. That work should reuse current Job identity, immutable
JobVersions, observations, and lineage rather than changing the ingestion
foundation.
