import assert from "node:assert/strict";
import test from "node:test";
import {
  buildQuarantineHref,
  getQuarantineEmptyState,
  MAX_QUARANTINE_PAGE,
  parseQuarantineQuery,
  QUARANTINE_PAGE_SIZE,
} from "../lib/quarantine/query-state";
import { quarantineRunId, quarantineSourceId } from "./quarantine-fixtures";

test("quarantine URL state preserves valid scopes/status and trims bounded categories", () => {
  assert.deepEqual(
    parseQuarantineQuery({
      page: "2",
      status: "open",
      source: quarantineSourceId,
      run: quarantineRunId,
      category: " normalization_failed ",
    }),
    {
      page: 2,
      status: "open",
      source: quarantineSourceId,
      run: quarantineRunId,
      category: "normalization_failed",
    },
  );
  assert.equal(parseQuarantineQuery({ category: "   " }).category, undefined);
  assert.equal(
    Array.from(
      parseQuarantineQuery({ category: "🙂".repeat(101) }).category ?? "",
    ).length,
    100,
  );
});

test("invalid/repeated URL values use safe defaults without unsafe offsets", () => {
  for (const page of [
    "0",
    "-1",
    "1.5",
    "1e3",
    "9007199254740993",
    String(MAX_QUARANTINE_PAGE + 1),
    ["1", "2"],
  ])
    assert.equal(parseQuarantineQuery({ page }).page, 1);
  const repeated = parseQuarantineQuery({
    status: ["open", "resolved"],
    run: [quarantineRunId],
    source: [quarantineSourceId],
    category: ["a", "b"],
  });
  assert.deepEqual(repeated, {
    page: 1,
    status: undefined,
    run: undefined,
    source: undefined,
    category: undefined,
  });
  const invalid = parseQuarantineQuery({
    status: "failed",
    source: "http://other.test",
    run: "../run",
  });
  assert.equal(invalid.status, undefined);
  assert.equal(invalid.source, undefined);
  assert.equal(invalid.run, undefined);
  assert.ok((MAX_QUARANTINE_PAGE - 1) * QUARANTINE_PAGE_SIZE <= 2147483647);
});

test("pagination preserves every filter and applying filters resets page", () => {
  const state = parseQuarantineQuery({
    page: "3",
    status: "open",
    source: quarantineSourceId,
    run: quarantineRunId,
    category: "custom & unknown",
  });
  const url = new URL(
    buildQuarantineHref(state, { page: 4 }),
    "http://dashboard.test",
  );
  assert.deepEqual(Object.fromEntries(url.searchParams), {
    status: "open",
    source: quarantineSourceId,
    run: quarantineRunId,
    category: "custom & unknown",
    page: "4",
  });
  const applied = new URL(
    buildQuarantineHref(state, { page: 1, status: undefined }),
    "http://dashboard.test",
  );
  assert.equal(applied.searchParams.get("page"), null);
  assert.equal(applied.searchParams.get("status"), null);
  assert.equal(applied.searchParams.get("source"), quarantineSourceId);
  assert.equal(applied.searchParams.get("run"), quarantineRunId);
  assert.equal(applied.searchParams.get("category"), "custom & unknown");
  assert.equal(buildQuarantineHref({ page: 1 }), "/dashboard/quarantine");
});

test("unknown categories are preserved and URL syntax is encoded safely", () => {
  const category = "<script>&other=1#hash";
  const url = new URL(
    buildQuarantineHref({ page: 1, category }),
    "http://dashboard.test",
  );
  assert.equal(url.pathname, "/dashboard/quarantine");
  assert.equal(url.hash, "");
  assert.equal(url.searchParams.get("category"), category);
});

test("quarantine empty states distinguish dataset, filter misses and out-of-range pages", () => {
  assert.equal(getQuarantineEmptyState(0, { page: 1 }), "unfiltered");
  for (const state of [
    { page: 1, run: quarantineRunId },
    { page: 1, source: quarantineSourceId },
    { page: 1, category: "unknown" },
  ])
    assert.equal(getQuarantineEmptyState(0, state), "filtered");
  assert.equal(getQuarantineEmptyState(26, { page: 3 }), "page");
});
