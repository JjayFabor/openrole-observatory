import assert from "node:assert/strict";
import test from "node:test";
import {
  formatAbsoluteTimestamp,
  formatRelativeTimestamp,
  formatRunDuration,
  getPipelineStatusPresentation,
} from "../lib/dashboard/presentation";
import { pipelineStatuses } from "../lib/api/types";
import { pipelineRun } from "./fixtures";

test("pipeline presentation retains each backend status and distinguishes partial success", () => {
  assert.deepEqual(
    pipelineStatuses.map(
      (status) => getPipelineStatusPresentation(status).label,
    ),
    ["Pending", "Running", "Completed", "Completed with errors", "Failed"],
  );
  assert.notEqual(
    getPipelineStatusPresentation("completed_with_errors").className,
    getPipelineStatusPresentation("failed").className,
  );
});

test("absolute timestamps are deterministic UTC including midnight", () => {
  assert.equal(
    formatAbsoluteTimestamp("2026-10-09T14:42:00Z"),
    "Oct 9, 2026, 14:42:00 UTC",
  );
  assert.equal(
    formatAbsoluteTimestamp("2026-10-09T08:00:00+08:00"),
    "Oct 9, 2026, 00:00:00 UTC",
  );
  assert.equal(formatAbsoluteTimestamp(null), "Never");
  assert.equal(formatAbsoluteTimestamp("invalid"), "Unavailable");
});

test("relative timestamps use a supplied stable time for past and future", () => {
  const now = Date.parse("2026-10-09T15:00:00Z");
  assert.equal(
    formatRelativeTimestamp("2026-10-09T14:42:00Z", now),
    "18 min. ago",
  );
  assert.equal(
    formatRelativeTimestamp("2026-10-09T15:18:00Z", now),
    "in 18 min.",
  );
  assert.equal(
    formatRelativeTimestamp("2026-10-09T14:59:30Z", now),
    "30 sec. ago",
  );
  assert.equal(
    formatRelativeTimestamp("2026-10-09T13:00:00Z", now),
    "2 hr. ago",
  );
  assert.equal(
    formatRelativeTimestamp("2026-10-07T15:00:00Z", now),
    "2 days ago",
  );
  assert.equal(formatRelativeTimestamp(null, now), "Never");
  assert.equal(formatRelativeTimestamp("bad", now), "Unavailable");
});

test("duration formatting handles milliseconds, seconds, minutes and rounding carry", () => {
  for (const [completed_at, expected] of [
    ["2026-10-09T10:00:00.000Z", "0 ms"],
    ["2026-10-09T10:00:00.530Z", "530 ms"],
    ["2026-10-09T10:00:01Z", "1 s"],
    ["2026-10-09T10:00:04.200Z", "4.2 s"],
    ["2026-10-09T10:01:18Z", "1m 18s"],
    ["2026-10-09T10:01:59.999Z", "2m 0s"],
  ]) {
    assert.equal(formatRunDuration(pipelineRun({ completed_at })), expected);
  }
});

test("duration displays backend running/pending state without inferring it from null completion", () => {
  assert.equal(
    formatRunDuration(pipelineRun({ status: "running", completed_at: null })),
    "Running",
  );
  assert.equal(
    formatRunDuration(pipelineRun({ status: "pending", completed_at: null })),
    "—",
  );
  assert.equal(
    formatRunDuration(pipelineRun({ status: "failed", completed_at: null })),
    "Unavailable",
  );
});

test("duration rejects reversed or invalid timestamps", () => {
  assert.equal(
    formatRunDuration(pipelineRun({ completed_at: "2026-10-09T09:59:59Z" })),
    "Unavailable",
  );
  assert.equal(
    formatRunDuration(pipelineRun({ started_at: "invalid" })),
    "Unavailable",
  );
});
