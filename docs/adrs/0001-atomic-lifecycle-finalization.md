# ADR 0001: Commit lifecycle reconciliation with successful run finalization

Date: 2026-10-09 (Asia/Manila)

Status: Accepted during Phase 2 Task 33, following developer approval.

## Context

Task 31 originally committed present-state reset/reappearance, confirmation, and
first-absence detection in separate transactions before completing the run. A
later-stage or finalization failure could leave an absence confirmation attached
to a failed run. An integration test explicitly demonstrated that behavior.

Task 33 and the data-model invariant require failed runs to leave existing
lifecycle state unchanged. An absence decision and its successful run provenance
must therefore become durable together.

## Decision

After raw acquisition and canonical record processing finish, SourceSyncService
opens one database transaction. It passes the same AsyncSession through presence
validation, Task 30, Task 29, Task 28, and successful PipelineRun finalization.
Job lifecycle fields, JobLifecycleEvents, run status/metrics/completion time, and
SourceConnection.last_successful_sync_at commit together.

The lifecycle services and PipelineRunService accept an optional session. When
supplied, the caller owns commit/rollback. Standalone calls retain their original
transaction ownership. Each public entry point delegates to one implementation;
there are no separate reconciliation algorithms for the two invocation modes.

If a stage, finalization flush, or transaction commit fails, the shared transaction
rolls back before SourceSyncService attempts failed-run finalization in a separate
transaction. The source advisory lock remains held until that attempt finishes.

HTTP and ObjectStorage I/O occur before this transaction. Canonical record
processing continues to use independent per-record transactions. A failed sync
can retain valid canonical versions, change events, observations, and freshness
already persisted by that stage; it cannot retain this run's lifecycle decisions.

## Consequences

- Conservative lifecycle behavior now holds even for later-stage failures.
- The final database transaction lasts through three source-scoped lifecycle
  batches and finalization, but spans neither network I/O nor the entire sync.
- PostgreSQL row locks remain held until the shared commit/rollback.
- Stage logs describe prepared outcomes; the sync success log follows commit.
- No schema change or migration is required.
- A database outage can still prevent recording the failed status. That error is
  logged and reported; the system does not claim success when finalization fails.
- The overall sync remains partially durable because Bronze and canonical
  ingestion intentionally precede lifecycle reconciliation.

## Verification

The lifecycle integration suite injects failures after earlier stages, after
successful/completed-with-errors finalization flushes, and immediately before
commit. It verifies all lifecycle actions and event inserts roll back, successful
freshness stays unchanged, failure metrics survive, and the source lock releases.
The authoritative Phase 2 test also verifies multiple cycles and API lineage.
