# OpenRole Observatory — Phase 2 Implementation Specification

## 1. Purpose

Phase 2 turns the historical data collected in Phase 1 into job-lifecycle intelligence.

Phase 1 answered:

> Can OpenRole reliably fetch, preserve, normalize, version, and trace job listings?

Phase 2 answers:

> What changed, when did it change, is the listing still present, and what has happened to it over time?

The focus of Phase 2 is:

- field-level change detection;
- lifecycle state;
- disappearance detection;
- reappearance detection;
- change-event persistence;
- source freshness;
- pipeline observability;
- read APIs for job history.

Phase 2 must build on the existing Phase 1 architecture rather than redesigning ingestion.

---

# 2. Phase 2 Objective

The target workflow is:

```text
Successful source synchronization
        ↓
Current source observations
        ↓
Compare against previously observed jobs
        ↓
┌───────────────────┬────────────────────┐
│ Job still present │ Job not present    │
│                   │                    │
│ ↓                 │ ↓                  │
│ Version changed?  │ Presence tracking  │
│                   │                    │
│ ↓                 │ ↓                  │
│ Field-level diff  │ Confirm absence    │
│                   │                    │
│ ↓                 │ ↓                  │
│ Change events     │ Lifecycle event    │
└───────────────────┴────────────────────┘
        ↓
Job history / lifecycle API
```

Phase 2 should make OpenRole capable of explaining:

```text
Job first observed:
2026-09-20

Last observed:
2026-10-08

Changes:
2026-09-28
workplace_type:
remote → hybrid

2026-10-02
salary:
not stated → €65,000–€80,000

Lifecycle:
2026-10-08
still observed
```

Or:

```text
Lifecycle:
2026-10-02
first absent from successful source sync

2026-10-05
absence confirmed

Current status:
not_observed
```

And later:

```text
2026-10-08
listing reappeared
```

---

# 3. Core Principles

## 3.1 Observations are facts

OpenRole may say:

```text
Observed at source
Not observed at source
Reappeared at source
```

It must not infer:

```text
Employer cancelled hiring
Employer never intended to hire
Job is fake
Job is a ghost job
```

without direct evidence.

---

## 3.2 One missed observation is not automatically removal

A job may disappear temporarily because of:

- provider inconsistency;
- pagination issues;
- source synchronization delay;
- transient ATS behavior;
- deployment issues.

Therefore OpenRole should use conservative lifecycle rules.

---

## 3.3 Failed pipeline runs do not affect lifecycle

If a source synchronization fails:

```text
HTTP timeout
R2 failure
invalid top-level response
database failure
```

existing jobs must remain unchanged.

Only a successfully processed source snapshot may contribute to presence/absence decisions.

---

## 3.4 Historical versions remain immutable

Field-level changes must be derived from:

```text
previous JobVersion
vs
new JobVersion
```

Do not rewrite historical canonical content.

---

## 3.5 Change events are derived facts

`JobVersion` remains the canonical historical state.

A `JobChangeEvent` is a derived representation that makes common change queries easier.

The version history remains the source of truth.

---

# 4. In Scope

Phase 2 includes:

- deterministic field-level diff engine;
- `job_change_events`;
- lifecycle event modeling;
- source-run presence reconciliation;
- conservative absence confirmation;
- job transition to not-observed;
- job reappearance;
- lifecycle history;
- job history API;
- job changes API;
- lifecycle API;
- source freshness information;
- basic pipeline observability;
- tests for lifecycle and change behavior;
- documentation.

---

# 5. Explicitly Out of Scope

Do NOT implement in Phase 2:

- Lever;
- Ashby;
- Workable;
- LinkedIn scraping;
- Indeed scraping;
- AI enrichment;
- skill extraction;
- sponsorship extraction;
- relocation classification;
- semantic duplicate detection;
- cross-source entity resolution;
- saved searches;
- user authentication;
- subscriptions;
- payments;
- email alerts;
- public webhooks;
- dbt;
- DuckDB;
- Parquet marts;
- Kafka;
- Spark;
- recommendation systems.

These belong to later phases.

---

# 6. Field-Level Change Detection

When Task 20 creates:

```text
Version N
→
Version N+1
```

Phase 2 should compare the canonical values.

Example:

```text
Version 1:
title = Backend Engineer
location_text = Remote
workplace_type = remote
salary_min = null
salary_max = null

Version 2:
title = Backend Engineer
location_text = Berlin
workplace_type = hybrid
salary_min = 65000
salary_max = 80000
```

Derived changes:

```text
location_text:
Remote → Berlin

workplace_type:
remote → hybrid

salary_min:
null → 65000

salary_max:
null → 80000
```

---

# 7. Fields Initially Tracked for Change

Track canonical user-relevant fields such as:

```text
title
description
location_text
city
region
country_code
workplace_type
employment_type
salary_min
salary_max
salary_currency
salary_period
source_url
canonical_metadata
```

Do not automatically track:

```text
created_at
effective_from
effective_to
is_current
version_number
source_observation_id
source_updated_at
```

unless there is a clear product reason.

These are operational/provenance fields rather than user-facing material content changes.

---

# 8. Description Change Handling

Job descriptions may be large.

Phase 2 should detect:

```text
description changed
```

but should not necessarily store an entire duplicate description inside `job_change_events`.

The historical values already exist in:

```text
JobVersion
```

A change event may instead record:

```text
field_name = description
change_type = modified
```

and optionally compact metadata.

The API can retrieve the before/after versions when detailed comparison is required.

---

# 9. Change Types

Initial change categories:

```text
added
removed
modified
```

Examples:

```text
salary_min:
null → 65000
= added

workplace_type:
remote → hybrid
= modified

salary_currency:
EUR → null
= removed
```

Field-value removal does not assert that an employer removed a listing. Lifecycle
status uses the factual term `not_observed`.

---

# 10. `job_change_events`

Introduce a derived event table.

Conceptual fields:

```text
id

job_id
from_version_id
to_version_id

field_name
change_type

old_value
new_value

detected_at

created_at
```

The exact representation of `old_value` and `new_value` should be designed carefully.

Possible options:

```text
JSONB
TEXT
```

Prefer JSONB if values may include:

- strings;
- numbers;
- nulls;
- arrays;
- structured metadata.

---

# 11. Change Event Constraints

A change event must identify:

```text
Job
From Version
To Version
Field
```

Consider uniqueness:

```text
UNIQUE(
    from_version_id,
    to_version_id,
    field_name
)
```

This helps prevent duplicate event generation during retries.

---

# 12. Diff Engine

Implement field comparison as pure Python.

Conceptually:

```text
JobVersion A
+
JobVersion B
        ↓
diff_job_versions()
        ↓
list[FieldChange]
```

It must not:

- access PostgreSQL;
- call AI;
- call Greenhouse;
- mutate versions.

## Task 25 implementation

`app/jobs/change_detection.py` accepts two `JobVersionComparable` frozen dataclass
snapshots and returns `list[FieldChange]`. The snapshots contain material values
only. `JobVersionComparable.from_canonical_job()` explicitly copies a validated
`CanonicalJobInput`, converts its URL to a string, and copies nested metadata.
Callers must construct snapshots before comparison; the diff function does not
read ORM objects or relationships.

`FieldChange` and the shared `FieldChangeType` live in the pure
`app/jobs/changes.py` module. Task 24's ORM module re-exports the same enum for
compatibility without requiring the diff engine to import persistence code.
Frozen dataclasses prevent attribute reassignment; contained JSON dictionaries
and lists are ordinary containers. Normalization copies those containers, so
editing a result cannot alter the input metadata.

`TRACKED_JOB_FIELDS` fixes the output order:

```text
title, description, location_text, city, region, country_code,
workplace_type, employment_type, salary_min, salary_max,
salary_currency, salary_period, source_url, canonical_metadata
```

These are exactly Task 10's material hash fields. Job/version IDs, external job
ID, source observation ID, version number, content hash, effective dates,
current-version flags, source publication/update timestamps, and creation time
are excluded because they describe identity, provenance, or processing rather
than material content.

The hash and diff share `normalize_canonical_job_values()` in `hashing.py`:

- `None` remains null; empty strings and whitespace are not reinterpreted.
- Finite Decimal salaries become normalized non-exponent strings without float
  conversion: `65000.00` becomes `"65000"`, `0.10` becomes `"0.1"`, and zero
  becomes `"0"`. Equivalent decimal scales do not create a change.
- Enums use their underlying values. The existing datetime normalizer converts
  aware values to UTC ISO 8601 with `Z` and rejects naive datetimes; no current
  tracked top-level field is a datetime.
- Metadata compares as JSON structures, ignoring dictionary key insertion order.
  Only the outer `departments` and `offices` lists ignore element order, matching
  the material hash. Other lists, including nested collections, preserve order.
- Unsupported objects, non-string dictionary keys, and non-finite numeric values
  raise clear errors instead of being silently stringified.

After normalization, equal values produce no change. `None → non-null` is
`added`; `non-null → None` is `removed`; other unequal values are `modified`.
Comparison preserves JSON value distinctions that Python equality otherwise
collapses, such as `true` versus `1`, `1` versus `1.0`, and signed floating-point
zero. This keeps diff explanations aligned with material hash bytes.

Description changes include the complete old/new canonical text in memory.
Task 25 introduces no HTML cleanup, semantic diffing, or highlighting. Task 26
persists these complete values, including descriptions, without compact markers
or a separate serialization policy.

Task 25 generates no IDs or timestamps, mutates no input state, performs no I/O,
and persists no events. Its unit tests can run independently of database fixtures:

```bash
DATABASE_URL=unavailable uv run pytest --confcutdir=tests/unit tests/unit/jobs
```

The tests also verify every tracked field against Task 10 hashes, compare the
existing Greenhouse fixtures through canonical mapping, and run the engine in a
fresh process with database/API/storage imports blocked.

---

# 13. Diff Determinism

The same pair of versions must always produce the same changes.

Change ordering should also be deterministic.

Example:

```text
title
location_text
workplace_type
salary_min
salary_max
```

or another explicit field order.

Do not rely on arbitrary dictionary iteration when user-facing output depends on ordering.

---

# 14. Change Event Integration

When a new JobVersion is created in the changed path:

```text
current Version N
↓
new Version N+1
```

Phase 2 should generate field-change events in the same logical operation.

Preferred:

```text
BEGIN

close Version N
create Version N+1
generate diff
persist JobChangeEvents

COMMIT
```

If event persistence fails:

the version transition should not partially commit.

This keeps version and derived change history consistent.

## Task 26 implementation

`ChangedJobPersistenceService` extends the existing transaction and row locks.
It closes and flushes Version N before inserting Version N+1, satisfying the
partial unique index that permits only one current version per job. Flushing the
new version provides its UUID for event foreign keys; flush sends SQL but does
not commit, so all writes remain reversible.

The service copies both versions' material fields into `JobVersionComparable`
snapshots, including a deep copy of metadata, and invokes `diff_job_versions()`
exactly once. Each `FieldChange` maps directly to one `JobChangeEvent`: IDs come
from the locked Job and the two versions, classification uses the diff enum's
value, and old/new JSON values are preserved. `detected_at` is the observation's
`observed_at`, also used as the new version's `effective_from`. Full descriptions
are retained; large Unicode descriptions and nested metadata are tested through
PostgreSQL JSONB.

`JobRepository.add_change_events()` adds all rows and flushes in the same session.
The service then advances `last_seen_at`, and the enclosing transaction commits
once. There is no separate event transaction or commit per event. JobVersion
remains authoritative; event rows are derived explanations and are not inputs
to future version creation.

Different content hashes with an empty diff raise `JobDiffInvariantError`
(`JOB_DIFF_INVARIANT_FAILED`). Diff generation or event insertion failure rolls
back the old version's closure, the new version, every event, and freshness.
The existing observation/version checks prevent replayed transitions, while
`uq_job_change_events_from_to_field` is the final duplicate-event safeguard.
Event integrity failures propagate as `ChangedJobDatabaseError` with the original
database error as the cause; they are neither ignored nor upserted.

Initial Version 1 and unchanged observations create no change events, because
there is no transition between different historical states. Task 26 adds no
lifecycle events, absence behavior, APIs, or migrations.

---

# 15. Lifecycle Concept

A job has a lifecycle independent from content versioning.

Example:

```text
Observed
↓
Not observed
↓
Observed again
```

A listing can disappear without its canonical content changing.

Therefore lifecycle changes must not require creation of a new JobVersion.

---

# 16. Lifecycle Status

Keep the persistent current status simple.

Recommended:

```text
observed
not_observed
```

Do not use:

```text
reappeared
```

as a permanent status.

Why?

Reappearance is an event.

After reappearing, the current job status is simply:

```text
observed
```

---

# 17. Lifecycle Events

Introduce:

```text
job_lifecycle_events
```

Conceptual fields:

```text
id
job_id
pipeline_run_id

event_type

occurred_at

previous_status
new_status

metadata

created_at
```

Initial event types:

```text
first_observed
absence_detected
not_observed_confirmed
reappeared
```

Whether `first_observed` is necessary should be evaluated.

It can also be derived from:

```text
jobs.first_seen_at
```

Avoid storing redundant events without value.

---

# 18. Presence Reconciliation

After a successful source synchronization, OpenRole knows:

```text
Which external job IDs appeared in this source snapshot?
```

It also knows:

```text
Which jobs are currently considered observed for this SourceConnection?
```

Phase 2 should compare those sets.

Example:

```text
Previously observed:
1001
1002
1003

Current successful run:
1001
1003

Potentially absent:
1002
```

---

# 19. Presence Reconciliation Input

Use:

```text
PipelineRun
+
SourceConnection
+
SourceObservations from this run
```

Do not parse RawSnapshot again unnecessarily.

Task 17 already produced valid observations.

---

# 20. Invalid Records and Presence

A record that appears in the raw source but is quarantined due to malformed data creates an important ambiguity.

If OpenRole can recover a valid:

```text
external_job_id
```

from the invalid record, do NOT automatically treat that job as absent.

Recommended:

> Include recoverable external IDs from quarantined records in the "present at source" set.

Reason:

The listing was present, even though OpenRole could not normalize it.

This avoids incorrectly marking jobs absent due to a parser/schema problem.

Document this carefully.

---

# 21. Failed Source Run

Presence reconciliation must not execute for:

```text
failed
```

pipeline runs.

A failed run provides no reliable absence evidence.

---

# 22. Conservative Absence Confirmation

Do not immediately change:

```text
observed
→ not_observed
```

after the first successful run in which the listing is absent.

Recommended Phase 2 policy:

```text
First consecutive successful absence:
record absence_detected

Second consecutive successful absence:
confirm not_observed
```

This reduces false removals caused by temporary source anomalies.

---

# 23. Absence Tracking

The system needs enough state to know:

```text
How many consecutive successful source runs have omitted this job?
```

Possible strategies:

## Option A

Add fields to `jobs`:

```text
consecutive_absent_runs
absence_first_detected_at
```

## Option B

Derive from lifecycle events/pipeline runs.

For Phase 2, Option A is simpler and more efficient.

Recommended additions:

```text
consecutive_absent_runs INTEGER NOT NULL DEFAULT 0
absence_first_detected_at TIMESTAMPTZ NULL
```

This is a schema change and should be documented/migrated deliberately.

---

# 24. Absence State Rules

For an observed Job:

## Present in successful source run

Set:

```text
consecutive_absent_runs = 0
absence_first_detected_at = NULL
```

Current status remains:

```text
observed
```

---

## Missing for first successful run

Set:

```text
consecutive_absent_runs = 1
absence_first_detected_at = run observation time
```

Create lifecycle event:

```text
absence_detected
```

Status remains:

```text
observed
```

The job is not yet confirmed missing.

---

## Missing for second consecutive successful run

Set:

```text
consecutive_absent_runs = 2
lifecycle_status = not_observed
no_longer_observed_at = current run time
```

Create:

```text
not_observed_confirmed
```

Do not create another JobVersion.

---

# 25. Configurable Threshold

Do not build organization/user customization yet.

Define a Phase 2 application setting such as:

```text
JOB_ABSENCE_CONFIRMATION_RUNS=2
```

or a code-level clearly documented constant.

If configuration is easy and consistent with existing Settings, environment configuration is acceptable.

Do not over-engineer policy storage.

Task 29 implements this setting in `Settings` with default 2 and validation that
accepts exactly 2. Phase 2 deliberately rejects values below or above 2. The
current schema records first detection and confirmation events, but cannot prove
which intermediate runs incremented a counter without an event. Supporting
larger thresholds safely would require a separate persistence design and review.

---

# 26. Reappearance

Suppose:

```text
Job 1002
status = not_observed
```

A later successful run contains:

```text
external_job_id = 1002
```

Then:

```text
lifecycle_status = observed
consecutive_absent_runs = 0
absence_first_detected_at = NULL
reappeared_at = observation time
```

Create lifecycle event:

```text
reappeared
```

---

# 27. Reappearance and Content

Reappearance can happen with:

```text
same canonical content
```

or:

```text
changed canonical content
```

These are independent dimensions.

Example:

```text
Job reappears
+
description changed
```

The same processing may create:

```text
reappeared lifecycle event
+
new JobVersion
+
field change events
```

Keep lifecycle and version logic separate but composable.

---

# 28. `last_seen_at`

When a listing reappears or remains observed:

```text
last_seen_at
```

continues to reflect the latest valid observation.

Absence reconciliation must not update `last_seen_at`.

---

# 29. `no_longer_observed_at`

Set only when absence becomes confirmed.

Do not set it on first potential absence.

---

# 30. `reappeared_at`

Set when a previously confirmed not-observed job becomes observed again.

This field represents the most recent reappearance.

Detailed multiple reappearance history belongs in:

```text
job_lifecycle_events
```

---

# 31. Presence Reconciliation Transaction Strategy

Do not lock every source job in one massive transaction unnecessarily.

Possible approach:

1. obtain the set of IDs observed in the successful run;
2. query candidate active jobs for that SourceConnection;
3. update lifecycle state in controlled transactions/batches.

Preserve correctness over premature optimization.

Document concurrency assumptions.

---

# 32. Sync Lock Relationship

Phase 1 already ensures only one sync per SourceConnection executes at a time.

This simplifies lifecycle reconciliation.

Presence reconciliation should execute while the source-level synchronization lock is still held.

That prevents two successful runs from racing on absence counters.

---

# 33. Lifecycle Timing

Use one consistent run-level timestamp.

Possible:

```text
RawSnapshot.retrieved_at
```

or:

```text
PipelineRun.completed_at
```

Recommended:

> Use the RawSnapshot retrieval/observation time for source-presence semantics.

This reflects when OpenRole observed the ATS state.

Document the choice.

---

# 34. Lifecycle Events Are Immutable

Once created:

```text
JobLifecycleEvent
```

should generally not be edited.

Corrections should be exceptional administrative operations outside Phase 2.

---

# 35. Pipeline Integration

Presence reconciliation should execute only after record processing has successfully completed enough to trust the source membership set.

Recommended pipeline ordering:

```text
fetch raw
↓
validate source
↓
process records
↓
presence reconciliation
↓
finalize PipelineRun
```

This means Task 21/22 orchestration will require a controlled extension.

Do not duplicate synchronization logic.

---

# 36. Partial Success and Presence Reconciliation

A `completed_with_errors` run may still be usable for lifecycle reconciliation if missing/invalid records have recoverable external IDs.

However, be conservative.

Recommended Phase 2 rule:

Presence reconciliation may execute on a source-schema-valid run when:

- top-level response was valid;
- all raw records can be accounted for as:
  - successfully observed;
  - quarantined with recoverable external ID.

If any quarantined record lacks an external ID:

> Do not use that run as absence evidence.

Why?

One of those invalid records might correspond to a currently known job.

This prevents false lifecycle transitions.

---

# 37. Presence Confidence Result

The processing stage may return:

```text
presence_reconciliation_safe = true/false
```

or equivalent.

If false:

- record pipeline data normally;
- skip absence counter updates;
- log why lifecycle reconciliation was skipped.

Do not fail the entire ingestion merely because absence inference is unsafe.

---

# 38. Source Freshness

Phase 2 should expose source freshness information.

For each SourceConnection:

```text
last_attempted_sync_at
last_successful_sync_at
last PipelineRun status
last successful record count
```

Future frontend can use this to show:

```text
Last successfully checked:
38 minutes ago
```

---

# 39. Pipeline Observability

Add read/query support for:

- latest source run;
- recent failures;
- quarantined-record count;
- sync duration if derivable;
- last successful synchronization.

Do not introduce Prometheus/Grafana unless already justified.

PostgreSQL + structured logs are enough.

---

# 40. Job History API

Add:

```http
GET /api/v1/jobs/{job_id}/versions
```

if not already available.

Return version history in chronological or reverse chronological order.

Document ordering.

Recommended:

```text
version_number ASC
```

for historical reconstruction.

---

# 41. Job Change API

Add:

```http
GET /api/v1/jobs/{job_id}/changes
```

Return:

```text
field
change_type
old_value
new_value
from_version
to_version
detected_at
```

Support simple pagination if necessary.

---

# 42. Job Lifecycle API

Add:

```http
GET /api/v1/jobs/{job_id}/lifecycle
```

Return:

- current lifecycle status;
- first_seen_at;
- last_seen_at;
- no_longer_observed_at;
- reappeared_at;
- absence counter;
- lifecycle events.

---

# 43. Job Detail API

If an existing Job read endpoint exists, enrich it with:

```text
current lifecycle status
first seen
last seen
current version
```

Do not build full search yet.

---

# 44. Source Health API

Add or enrich:

```http
GET /api/v1/sources/{source_id}
```

or equivalent administrative inspection endpoint.

Potential response:

```text
provider
active
last_attempted_sync_at
last_successful_sync_at
latest_run_status
```

Keep it administrative.

---

# 45. No Frontend Required Initially

Phase 2 can be completed through APIs and tests.

A lightweight internal dashboard may be added only as the final Phase 2 task if desired.

The data-engineering functionality must not depend on a frontend.

---

# 46. Phase 2 Data Model Changes

Expected additions:

```text
job_change_events
job_lifecycle_events
```

Expected changes to:

```text
jobs
```

Potential new fields:

```text
consecutive_absent_runs
absence_first_detected_at
```

Do not add unrelated schema.

---

# 47. Phase 2 Suggested Task Breakdown

Continue after Phase 1 Task 23 using small tasks.

## Task 24 — Phase 2 Schema Foundation

Implement:

```text
job_change_events
job_lifecycle_events
jobs.consecutive_absent_runs
jobs.absence_first_detected_at
```

Migration + constraints + tests only.

No behavior yet.

---

## Task 25 — Pure Field Diff Engine

Implement:

```text
JobVersion A
+
JobVersion B
↓
FieldChange[]
```

Pure Python only.

No database persistence.

---

## Task 26 — Persist Change Events

Extend changed-job transition so:

```text
Version N → Version N+1
```

also persists deterministic field-change events atomically.

---

## Task 27 — Presence Set Builder

From one successfully processed PipelineRun, build:

```text
observed external IDs
+
recoverable quarantined external IDs
```

and determine:

```text
presence_reconciliation_safe
```

No lifecycle mutation yet.

### Task 27 implementation

`PresenceSetBuilder(session).build_presence_set(pipeline_run_id)` consumes
persisted outcomes in the caller's SQLAlchemy session. It performs projection
queries for run metrics, observations, and quarantines, using snapshot metadata
to validate lineage and the processed record count. It never reads Bronze bytes
or uses ObjectStorage, and it does not query or mutate Jobs.

Run-ID-only calls accept only `completed` and `completed_with_errors`. Task 31
also supplies an internal `PresenceRun` handoff from successful record processing
for a still-`running` run. Its expected record outcome and metrics are validated
against durable snapshot and processing rows; it does not finalize or change the
stored run status. The handoff must match the stored run/source, and is rejected
for pending, failed, or terminal runs. Ordinary running-run calls remain rejected.
Missing runs use
the existing `PipelineRunNotFoundError`; non-successful states raise
`PresenceReconciliationNotAllowedError`. A successful run must have a processed
snapshot whose `record_count` equals `records_fetched`, including zero for a
verified empty board.

Phase 1 records observations before canonical processing. A later mapping,
hashing, or other record-level processing failure retains the observation and
adds quarantine for the same raw record. Therefore the correct persisted-count
checks are:

```text
records_fetched = records_valid + records_quarantined
persisted quarantine count = records_quarantined
persisted observation count - quarantined observation overlaps = records_valid
```

An overlap is identified by `(raw_snapshot_id, raw_record_locator)`, never by
external ID alone. A valid record and a quarantined duplicate ID at another
locator are separate source records. Counts remain record counts even though
the output ID sets deduplicate identity. Null locators cannot prove an overlap.
Conflicting IDs at one overlap, duplicate raw outcomes, unusable observation
IDs, count disagreements, and source/snapshot-run lineage mismatches raise
`PresenceDataInvariantError` rather than masquerading as ordinary unsafe runs.

`PresenceSetResult` is a frozen dataclass containing immutable sets:

- `observed_external_job_ids`: observations with no quarantine for the same raw
  record, representing successful canonical processing in the record stage.
- `recoverable_quarantine_external_job_ids`: usable IDs from all quarantine
  outcomes, including observations later quarantined and resolved quarantine.
- `present_external_job_ids`: a property returning the union of both sets.

Stored ID case and content are preserved. Null, empty, and whitespace-only
quarantine IDs are unidentified; any such row makes reconciliation unsafe with
reason `unidentified_quarantine_records`, while known IDs remain available for
diagnostics. Safe partial success and verified empty boards remain usable.
`observed_record_count` reports actual observation rows, including later
quarantined overlaps; it is not an alias for `records_valid`.

---

## Task 28 — Absence Detection

Implement:

```text
observed job absent from successful run
→ increment absence counter
→ first absence event
```

Do not confirm removal yet.

### Task 28 implementation

`FirstAbsenceDetectionService.detect_first_absences(pipeline_run_id)` builds
Task 27 presence evidence internally, using only stored rows. Unsupported or
failed runs, invalid evidence, and unsafe presence cause an exception before
Job updates. The service then locks the source's currently `observed` Jobs in
Job ID order and subtracts `present_external_job_ids` from their external IDs.
Recoverable quarantine IDs therefore prevent false absence signals.

Only missing Jobs with `consecutive_absent_runs == 0` are updated: the count
becomes exactly 1 and `absence_first_detected_at` becomes
`RawSnapshot.retrieved_at`. Their lifecycle status remains `observed`. The
matching `absence_detected` event records `observed` as both previous and new
status, the same observation time, Job/run provenance, and metadata
`{"consecutive_absent_runs": 1}`. Task 29 owns the confirmation-threshold setting.

Present Jobs are unchanged, including tentative absence state; Task 30 owns
resets. Missing Jobs with any positive count are skipped without overwriting
their first-absence timestamp. `not_observed` Jobs are excluded from the query.
A safe empty board can produce a first absence for every eligible source Job.
Freshness, historical removal/reappearance timestamps, canonical versions,
field-change events, and PipelineRun metrics are not changed.

All updates and event inserts share one batch transaction. Failure rolls back
the entire batch, including previously flushed events. Normal repeated calls
skip the count-one Jobs; the existing unique Job/run/event-type constraint
provides final duplicate protection. A replay after a later reset can safely
fail that constraint and roll back. Mutating reconciliation rejects a snapshot
time older than the Job's current freshness or lifecycle evidence. A count-zero
Job with an existing first-absence timestamp raises an invariant error rather
than overwriting inconsistent state.

`FirstAbsenceDetectionResult` reports `evaluated_jobs` (all source-scoped observed
Jobs), `first_absences_detected`, and `skipped_already_absent` (missing Jobs with
positive counters). Task 28 remains independently callable and Task 31 invokes
it last during source synchronization.

---

## Task 29 — Confirm Not Observed

Implement confirmation threshold:

```text
consecutive absence threshold reached
→ lifecycle_status = not_observed
→ no_longer_observed_at
→ lifecycle event
```

### Task 29 implementation

`AbsenceConfirmationService.confirm_absences(pipeline_run_id)` reads the validated
application setting and rebuilds Task 27 presence evidence within one database
transaction. Failed/unsupported runs, invalid evidence, and unsafe presence
raise before any Job mutation. Safe partial runs and safe empty boards remain
eligible. There is no network or object-storage I/O in this transaction.

The service locks only the run's source Jobs with status `observed` and positive
absence counts, ordered by Job ID. Jobs in `present_external_job_ids`, including
recoverable quarantine IDs, are left unchanged; Task 30 owns their reset.
Count-zero and `not_observed` Jobs are excluded by the query.

Before applying a missing Job, the service checks for an `absence_detected` or
`not_observed_confirmed` event for that Job and the current run. Either means
the run has already counted and is skipped. This prevents Task 28 and Task 29
from counting the same observation twice, and prevents old-run replay from
counting toward a later lifecycle cycle. Ordinary confirmation retries also
exclude Jobs whose status already became `not_observed`. The existing event
uniqueness constraint remains the final database safeguard.

Under the two-run policy, a missing eligible Job must have count 1 and an
existing first-absence timestamp. Inconsistent state raises an invariant error.
The confirmation observation must be strictly later than first detection and
must not predate the Job's current freshness or lifecycle evidence.

The counter advances to 2, status becomes `not_observed`, and
`no_longer_observed_at` becomes `RawSnapshot.retrieved_at`. This means OpenRole
obtained the observation satisfying its confirmation rule at that time; it does
not identify the exact employer removal time. `absence_first_detected_at`,
`first_seen_at`, `last_seen_at`, and `reappeared_at` are preserved.

A `not_observed_confirmed` event records `observed → not_observed`, Job/run
provenance, the same observation timestamp, and actual count/threshold metadata.
All state updates and events flush and commit together. An error rolls back the
entire batch, including earlier flushed inserts. No JobVersion, JobChangeEvent,
or PipelineRun metric is created or modified; no migration is needed.

`AbsenceConfirmationResult` returns `evaluated_jobs` (source-scoped observed Jobs
with positive counters), `confirmed_not_observed`, `skipped_present`, and
`skipped_already_applied`. Successful processing logs one summary.

These services rely on chronological run processing and present-state reset
between absence cycles. Task 31 now orchestrates them under SourceSyncService's
source lock; Task 29 does not scan intervening runs or perform resets itself.

---

## Task 30 — Reappearance

Implement:

```text
not_observed job appears again
→ lifecycle_status = observed
→ reset absence state
→ reappeared lifecycle event
```

Ensure it composes with unchanged/changed content processing.

### Task 30 implementation

`PresentJobReconciliationService.reconcile_present_jobs(pipeline_run_id)` builds
Task 27 evidence inside one batch transaction and raises
`PresenceReconciliationUnsafeError` before querying Jobs when that evidence is
unsafe. It reads `RawSnapshot.retrieved_at` as the lifecycle timestamp, selects
only present Jobs for the run's source, and locks them with `FOR UPDATE` in a
consistent ID order.

| Current Job state | Evidence | Action |
| --- | --- | --- |
| observed, no tentative absence | successful observation or quarantine presence | No write or event |
| observed, tentative absence | successful observation or quarantine presence | Clear count and first-absence timestamp; no event |
| not_observed | successful canonical observation | Return to observed; clear absence state; set reappeared_at; insert reappeared event |
| not_observed | quarantine presence only | No lifecycle change or event |

A provider-valid observation later quarantined is presence-only evidence; it
cannot confirm reappearance. A valid record with a quarantined duplicate at a
different locator still supplies successful evidence. This distinction is why
Task 27 exposes both sets separately.

`no_longer_observed_at` retains the most recent confirmed absence timestamp after
reappearance. The event records `not_observed → observed`, the run, retrieval
time, previous absence count, and previous confirmation timestamp. Historical
events preserve earlier cycles; these current timestamp fields summarize the
latest relevant transition.

Tasks 18–20 continue to own `last_seen_at`; Task 30 does not update freshness,
create versions, or create field-change events. Existing unchanged/changed paths
can run before present reconciliation: unchanged content reappears without a new
version, while changed content can produce both version/change-event history and
a separate reappearance event.

Job updates and lifecycle-event inserts flush and commit together. Any failure,
including a duplicate-event integrity error after another insert, rolls back the
entire batch. A repeated successful invocation sees healthy observed state and
does nothing; `uq_job_lifecycle_events_job_run_type` remains the final safeguard.
Mutating reconciliation rejects observation times older than the Job's existing
freshness or lifecycle evidence, preventing an old run from clearing newer state.

Tasks 28 and 29 detect and confirm absences. Task 30 tests also seed lifecycle
states independently. Task 31 integrates these independently callable services
into SourceSyncService with present reconciliation first.

---

## Task 31 — Pipeline Lifecycle Reconciliation

Integrate presence reconciliation into SourceSyncService while source lock is held.

Handle:

```text
safe lifecycle reconciliation
unsafe lifecycle reconciliation
failed run
partial-success run
```

### Task 31 implementation

SourceSyncService owns terminal finalization for normal syncs. It holds the same
session-level advisory lock from run creation through fetch/storage, record
processing, lifecycle processing, and finalization. Canonical record persistence
uses separate short transactions. Task 33 hardens lifecycle reconciliation and
successful finalization into one shared database transaction after that stage.

SnapshotIngestionOrchestrator now exposes `process_records()`, sharing the original
record routing and quarantine implementation with `process_snapshot()`. It returns
SnapshotIngestionResult with validated metrics and the expected successful terminal
outcome; the stored run remains running. Failure carries partial metrics, the
existing error classification, and the original exception as its cause, allowing
SourceSyncService to finalize failure once. The standalone `process_snapshot()`
entry point retains its original finalization contract.

The sync constructs an internal PresenceRun handoff from this successful result.
PresenceSetBuilder checks the stored running run/source, snapshot count, outcome
counts, and lineage. The handoff supplies final record-stage metrics without a
premature completed status or successful-sync timestamp write. Existing run-ID-only
lifecycle calls still require a completed/completed_with_errors run. No API accepts
caller-provided presence sets or running-run handoffs.

LifecycleReconciliationService first builds presence, then invokes:

1. present-state reset/reappearance (Task 30);
2. prior-absence confirmation (Task 29);
3. new first-absence detection (Task 28).

Confirmation therefore cannot consume a first absence created later in the same
run. Existing per-run event checks remain an additional idempotency safeguard.
Each mutation service revalidates the handoff in the caller's shared transaction.
Standalone calls retain their own atomic batch transactions.

Unidentified quarantine IDs produce an explicit skipped lifecycle result with
zero counts. Ingestion still completes with errors and advances the source's
successful-sync timestamp. Recoverable quarantine IDs permit lifecycle processing,
while remaining presence-only evidence for confirmed reappearance. Failed raw or
record processing never reaches lifecycle reconciliation.

Unexpected lifecycle errors propagate, fail the run with preserved record metrics,
and leave last_successful_sync_at unchanged. Logs identify presence_set,
present_reconciliation, absence_confirmation, or first_absence_detection. Task 33
rolls back all lifecycle stages and successful finalization together, including
when a later stage, finalization flush, or commit fails. Failed-run finalization
then uses a separate transaction while the lock is still held. Earlier canonical
record batches can remain committed; overall synchronization is not globally
atomic. [ADR 0001](adrs/0001-atomic-lifecycle-finalization.md) records this decision.

After lifecycle succeeds or safely skips, SourceSyncService finalizes completed or
completed_with_errors according to quarantine count. SourceSyncResult includes a
nested LifecycleReconciliationResult with performed/skipped_reason and counts for
resets, reappearances, first absences, and confirmations. The existing sync endpoint
adds this summary while preserving its previous fields; the CLI prints counts or
an explicit membership-incomplete skip. No new endpoint, metric column, migration,
or scheduler is introduced.

---

## Task 32 — History & Lifecycle APIs

Implement:

```text
GET /jobs/{id}/versions
GET /jobs/{id}/changes
GET /jobs/{id}/lifecycle
```

plus source freshness inspection.

### Task 32 implementation

Five read-only administrative routes now expose persisted facts:

- `GET /api/v1/jobs/{job_id}`: logical identity, current lifecycle/freshness state,
  and the current canonical JobVersion, regardless of observed/not_observed status.
- `GET /api/v1/jobs/{job_id}/versions`: canonical history, version flags/effective
  intervals, content hashes and source-observation IDs, ordered by version number
  ascending.
- `GET /api/v1/jobs/{job_id}/changes`: Task 26 persisted field events with JSON
  before/after values and joined version numbers, ordered by destination version
  number, field name alphabetically, then event ID, all ascending.
- `GET /api/v1/jobs/{job_id}/lifecycle`: current state plus historical events,
  ordered by occurrence time, creation time, then event ID, all ascending.
- `GET /api/v1/sources/{source_id}`: safe source identity, active state, attempted
  and successful sync timestamps, and one latest PipelineRun selected by start
  time descending then ID descending.

Each history uses `limit=50`, `offset=0` by default, bounded to limits 1–100 and
nonnegative offsets. Version/change collections use `items`; lifecycle uses
`events` beside its current summary. Existing jobs can have empty histories;
unknown jobs/sources use the existing stable HTTP 404 envelope. Job detail treats
a missing current version as HTTP 500 `CURRENT_JOB_VERSION_MISSING`; it does not
manufacture canonical state or return a misleading null version.

JobQueryService joins the current version in one query. Histories use one identity
check/current-state query and one bounded history query. Change queries select
event values and scalar version numbers, avoiding canonical description loads
and per-event lazy reads. SourceQueryService projects only safe source fields and
uses `LIMIT 1` for the latest run. Typed read schemas preserve JSON values, exact
Decimal salary strings, timezone-aware timestamps, and event metadata without
exposing SQLAlchemy's reserved `metadata` attribute.

`no_longer_observed_at` is OpenRole's confirmation observation time. Current
observed state can retain this historical timestamp and `reappeared_at` after a
return; paginating events never changes that current summary. The latest failed
run can coexist with an older `last_successful_sync_at`. Source configuration
and external account keys are excluded; existing safe run error fields remain
available. These internal endpoints still require external access control and
add neither authentication nor migrations.

Query services only read stored rows and construct response schemas inside their
sessions. They never commit domain mutations, call sync/lifecycle services, or
read Bronze objects. PostgreSQL API tests verify unchanged rows across every
registered table after all five GETs, plus version/change/lifecycle histories,
ordering ties, pagination, stable errors, source health, and sensitive-field
exclusion. Task 33 owns overall Phase 2 closure.

---

## Task 33 — Phase 2 End-to-End Verification

Test:

- field changes;
- first absence;
- confirmed absence;
- reappearance;
- reappearance + changed content;
- failed source does not affect lifecycle;
- unsafe partial run does not affect absence counters;
- history API;
- lifecycle API;
- documentation reconciliation.

Produce:

```text
docs/phase-2-completion.md
```

No Phase 3 features.

### Task 33 implementation

`test_authoritative_phase_two_history_and_api_story` runs actual SourceSyncService,
the Greenhouse HTTP client over mocked transport, filesystem ObjectStorage,
canonical persistence, lifecycle reconciliation, and read queries/routes against
real PostgreSQL. It covers initial/unchanged ingestion, one workplace change,
multiple field changes, first absence, explicit same-run confirmation rejection,
tentative reset, two confirmed absence/reappearance cycles, unchanged and changed
returns, and a successful-then-failed source-health story. Stored versions remain
the reconstructable canonical source of truth even without derived change events.

The fixture mapper uses the orchestrator's existing mapper injection point to
provide controlled workplace/employment/salary values. Production Greenhouse
mapping still leaves those fields unknown; no extraction feature was added.

Additional acceptance cases prove known quarantine presence, unidentified unsafe
membership, timeout/503/storage/invalid-JSON/database/event failures, verified
empty boards, source isolation, and a 100-job initial/unchanged/subset scenario.
Session-event checks prove application transactions do not span HTTP/storage I/O.
Existing schema, diff, hash, per-transition atomicity, API, and lock tests remain
part of the normal suite.

Normal sync passes one session through lifecycle and successful finalization;
public standalone calls use the same logic with their own transaction. Failure
injection tests cover later stages, successful and partial-success finalization,
and immediately-before-commit errors, verifying state/event rollback and retained
record metrics. Stage logs now say prepared until the source-sync success log
follows commit. SQLAlchemy errors hide bound SQL parameters.

The completed requirement/evidence audit, clean migration results, limitations,
technical debt, and Phase 3 recommendation are recorded in
[phase-2-completion.md](phase-2-completion.md). Developer understanding remains a
separate review gate; automated passing tests cannot certify it.

---

# 48. Phase 2 Test Scenarios

At minimum Phase 2 should prove these scenarios.

---

## Scenario A — Material Change

Run 1:

```text
Backend Engineer
Remote
```

Run 2:

```text
Backend Engineer
Hybrid
```

Expected:

```text
Version 2 created

JobChangeEvent:
workplace_type
remote → hybrid
```

---

## Scenario B — No Change

Repeated identical source.

Expected:

```text
no JobChangeEvent
no new JobVersion
last_seen_at updated
```

---

## Scenario C — First Absence

Run 1:

```text
jobs = [1001, 1002]
```

Run 2:

```text
jobs = [1001]
```

Expected:

```text
1002:
consecutive_absent_runs = 1
status = observed
absence_detected event
```

---

## Scenario D — Confirmed Absence

Next successful run:

```text
jobs = [1001]
```

Expected:

```text
1002:
consecutive_absent_runs = 2
status = not_observed
no_longer_observed_at set
not_observed_confirmed event
```

---

## Scenario E — Failed Run

If Run 2 fails:

```text
1002 absence counter remains unchanged
```

No absence event.

---

## Scenario F — Unsafe Partial Run

Suppose one malformed job record has:

```text
external_job_id = unknown
```

Do not use that run as absence evidence.

Known jobs remain unchanged from a lifecycle perspective.

---

## Scenario G — Reappearance

Later run:

```text
jobs = [1001, 1002]
```

Expected:

```text
1002:
status = observed
absence counter = 0
reappeared_at set
reappeared event
```

---

## Scenario H — Reappearance With Changed Content

1002 returns with:

```text
Remote → Hybrid
```

Expected:

```text
reappeared lifecycle event
+
new JobVersion
+
field change event
```

These operations should remain logically consistent.

---

# 49. Phase 2 Metric Considerations

Do not overload Phase 1 metrics.

Phase 2 may eventually add:

```text
jobs_absence_detected
jobs_marked_not_observed
jobs_reappeared
change_events_created
```

Only add persistent PipelineRun counters if they provide operational value.

Avoid turning PipelineRun into a table with dozens of counters.

Derived queries may be sufficient initially.

---

# 50. Phase 2 Definition of Done

Phase 2 is complete when OpenRole can reliably answer:

1. What versions has this job had?
2. Which fields changed between versions?
3. When did OpenRole detect those changes?
4. Is the job currently observed at the direct source?
5. Has it disappeared?
6. Was disappearance confirmed conservatively?
7. Has it reappeared?
8. What source run caused each lifecycle decision?
9. When was the source last successfully checked?
10. Can these answers be retrieved through stable APIs?

---

# 51. Final Phase 2 Architecture

At completion:

```text
Greenhouse
    ↓
Phase 1 ingestion
    ↓
Job / JobVersion
    ↓
┌────────────────────────┐
│                        │
▼                        ▼
Diff Engine          Presence Engine
│                        │
▼                        ▼
JobChangeEvents      JobLifecycleEvents
│                        │
└───────────┬────────────┘
            ▼
     History APIs
```

Phase 1 remains responsible for reliable ingestion.

Phase 2 adds interpretation of historical and presence data.

---

# 52. Phase 2 Non-Goal Reminder

Do not move to additional ATS providers merely because Phase 1/2 Greenhouse support works.

Phase 2 is about making one source **deeply correct and historically useful** before making ingestion wider.

Phase 3 delivers the internal dashboard over Greenhouse data. Additional providers
including Lever and Ashby remain deferred to a separately approved future scope.
