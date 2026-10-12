import assert from "node:assert/strict";
import test from "node:test";
import {
  buildJobHistoryHref,
  MAX_HISTORY_PAGE,
  parseJobHistoryQuery,
} from "../lib/jobs/history-query";
import { jobId } from "./job-detail-fixtures";
test("history sections maintain independent bounded URL pages", () => {
  const state = parseJobHistoryQuery({
    versions: "2",
    changes: "3",
    lifecycle: "4",
  });
  assert.deepEqual(state, { versions: 2, changes: 3, lifecycle: 4 });
  assert.equal(
    buildJobHistoryHref(jobId, state, "changes", 5),
    `/dashboard/jobs/${jobId}?versions=2&changes=5&lifecycle=4#changes`,
  );
  assert.equal(
    buildJobHistoryHref(jobId, state, "versions", 1),
    `/dashboard/jobs/${jobId}?changes=3&lifecycle=4#versions`,
  );
});
test("invalid/repeated/oversized history pages safely default", () => {
  for (const value of [
    "-1",
    "0",
    "1.1",
    "invalid",
    String(MAX_HISTORY_PAGE + 1),
    ["2", "3"],
  ])
    assert.equal(parseJobHistoryQuery({ versions: value }).versions, 1);
  assert.equal(
    parseJobHistoryQuery({ versions: String(MAX_HISTORY_PAGE) }).versions,
    MAX_HISTORY_PAGE,
  );
});
