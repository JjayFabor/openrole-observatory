import assert from "node:assert/strict";
import test from "node:test";
import {
  getSourceSyncErrorOutcome,
  getSourceSyncPresentation,
} from "../lib/sources/sync-presentation";
import type { SourceSyncOutcome, SourceSyncResponse } from "../lib/api/types";

const result: SourceSyncResponse = {
  pipeline_run_id: "22222222-2222-4222-8222-222222222222",
  source_connection_id: "11111111-1111-4111-8111-111111111111",
  status: "completed",
  records_fetched: 1200,
  records_valid: 1198,
  records_quarantined: 2,
  jobs_new: 10,
  jobs_changed: 8,
  jobs_unchanged: 1180,
  started_at: "2026-10-09T10:00:00Z",
  completed_at: "2026-10-09T10:01:00Z",
};

test("success and partial summaries preserve actual metrics and distinct outcomes", () => {
  const success = getSourceSyncPresentation({ state: "result", result });
  assert.equal(success.title, "Synchronization completed");
  assert.match(
    success.message,
    /Fetched 1,200 records · New 10 · Changed 8 · Unchanged 1,180/,
  );
  const partial = getSourceSyncPresentation({
    state: "result",
    result: { ...result, status: "completed_with_errors" },
  });
  assert.equal(partial.title, "Completed with errors");
  assert.match(partial.message, /Quarantined 2/);
  assert.match(partial.className, /amber/);
});

test("defensive failed response never presents success", () => {
  const failed = getSourceSyncPresentation({
    state: "result",
    result: { ...result, status: "failed" },
  });
  assert.equal(failed.title, "Synchronization failed");
  assert.doesNotMatch(failed.message, /Synchronization completed|Fetched/);
});

test("known errors require both documented HTTP status and exact code", () => {
  for (const [status, code, reason] of [
    [404, "SOURCE_CONNECTION_NOT_FOUND", "not_found"],
    [409, "SOURCE_CONNECTION_INACTIVE", "inactive"],
    [409, "SOURCE_SYNC_ALREADY_RUNNING", "already_running"],
    [504, "SOURCE_REQUEST_TIMEOUT", "source_timeout"],
    [502, "SOURCE_REQUEST_FAILED", "source_request_failed"],
    [502, "SOURCE_RESPONSE_INVALID", "source_response_invalid"],
    [503, "RAW_STORAGE_FAILED", "raw_storage_failed"],
    [500, "DATABASE_WRITE_FAILED", "database_write_failed"],
    [500, "PIPELINE_INTERNAL_ERROR", "pipeline_internal_error"],
  ] as const) {
    assert.deepEqual(getSourceSyncErrorOutcome(status, code), {
      state: "error",
      reason,
      refresh: true,
    });
    assert.deepEqual(getSourceSyncErrorOutcome(400, code), {
      state: "error",
      reason: "request_failed",
      refresh: true,
    });
  }
});

test("transport timeout and unavailable backend preserve mounted detail and unknown outcome", () => {
  const timeout = getSourceSyncErrorOutcome(0, "TIMEOUT");
  assert.deepEqual(timeout, {
    state: "error",
    reason: "timeout_unknown",
    refresh: false,
  });
  assert.match(
    getSourceSyncPresentation(timeout).message,
    /result is unknown.*may still be running.*Refresh/,
  );
  for (const code of ["NETWORK_ERROR", undefined]) {
    const unavailable = getSourceSyncErrorOutcome(0, code);
    assert.deepEqual(unavailable, {
      state: "error",
      reason: "backend_unavailable",
      refresh: false,
    });
  }
  assert.deepEqual(getSourceSyncErrorOutcome(0, "INVALID_CONFIGURATION"), {
    state: "error",
    reason: "invalid_configuration",
    refresh: false,
  });
  assert.deepEqual(getSourceSyncErrorOutcome(0, "INVALID_SOURCE_ID"), {
    state: "error",
    reason: "invalid_source",
    refresh: false,
  });
});

test("unknown backend text is not returned or displayed and carries no invented run ID", () => {
  const outcome: SourceSyncOutcome = getSourceSyncErrorOutcome(
    500,
    "<script>private-token</script>",
  );
  assert.doesNotMatch(
    JSON.stringify(outcome),
    /script|private-token|pipeline_run_id/,
  );
  assert.doesNotMatch(
    JSON.stringify(getSourceSyncPresentation(outcome)),
    /script|private-token/,
  );
  assert.deepEqual(getSourceSyncErrorOutcome(200, "INVALID_RESPONSE"), {
    state: "error",
    reason: "invalid_response",
    refresh: true,
  });
});
