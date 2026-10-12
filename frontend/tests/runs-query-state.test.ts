import assert from "node:assert/strict";
import test from "node:test";
import { buildRunsHref, parseRunsQuery } from "../lib/runs/query-state";
import { pipelineStatuses } from "../lib/api/types";
import { MAX_HISTORY_PAGE } from "../lib/jobs/history-query";
import { sourceId } from "./fixtures";
test("run status/source/page URL state supports actual statuses and refresh-safe links", () => {
  for (const status of pipelineStatuses)
    assert.equal(parseRunsQuery({ status }).status, status);
  const state = parseRunsQuery({
    page: "2",
    status: "failed",
    source: sourceId,
  });
  assert.deepEqual(state, { page: 2, status: "failed", source: sourceId });
  assert.equal(
    buildRunsHref(state, { page: 3 }),
    `/dashboard/runs?status=failed&source=${sourceId}&page=3`,
  );
  assert.equal(
    buildRunsHref(state, { status: "completed_with_errors", page: 1 }),
    `/dashboard/runs?status=completed_with_errors&source=${sourceId}`,
  );
  assert.equal(buildRunsHref({ page: 1 }), "/dashboard/runs");
});
test("invalid/duplicate run filters and unsafe offsets use safe defaults", () => {
  for (const page of [
    "-5",
    "0",
    "1.2",
    String(MAX_HISTORY_PAGE + 1),
    ["1", "2"],
  ])
    assert.equal(parseRunsQuery({ page }).page, 1);
  assert.deepEqual(
    parseRunsQuery({
      page: "2",
      source: [sourceId, sourceId],
      status: "success",
    }),
    { page: 2, status: undefined, source: undefined },
  );
  assert.equal(parseRunsQuery({ source: "invalid" }).source, undefined);
});
