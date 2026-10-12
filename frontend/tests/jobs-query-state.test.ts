import assert from "node:assert/strict";
import test from "node:test";
import {
  buildJobsHref,
  getJobsEmptyState,
  hasJobsFilters,
  JOBS_PAGE_SIZE,
  MAX_JOBS_PAGE,
  parseJobsQuery,
} from "../lib/jobs/query-state";

const source = "11111111-1111-4111-8111-111111111111";

test("jobs query defaults are safe and valid filters remain committed URL state", () => {
  assert.deepEqual(parseJobsQuery({}), {
    page: 1,
    status: undefined,
    source: undefined,
    q: undefined,
  });
  assert.deepEqual(
    parseJobsQuery({
      page: "2",
      status: "not_observed",
      source,
      q: "  engineer  ",
    }),
    { page: 2, status: "not_observed", source, q: "engineer" },
  );
});

test("adversarial page values fall back without creating unsafe offsets", () => {
  for (const page of [
    "0",
    "-1",
    "1.5",
    "1e3",
    "Infinity",
    "NaN",
    " 2 ",
    "9007199254740993",
    String(MAX_JOBS_PAGE + 1),
    ["1", "2"],
  ]) {
    assert.equal(parseJobsQuery({ page }).page, 1);
  }
  const maximum = parseJobsQuery({ page: String(MAX_JOBS_PAGE) }).page;
  assert.ok((maximum - 1) * JOBS_PAGE_SIZE <= 2147483647);
});

test("duplicate and invalid filter values use safe defaults", () => {
  for (const params of [
    { status: "closed", source: "invalid" },
    {
      status: ["observed", "not_observed"],
      source: [source, source],
      q: ["a", "b"],
    },
    { source: "https://other.test", q: "   " },
  ]) {
    const query = parseJobsQuery(params);
    assert.equal(query.status, undefined);
    assert.equal(query.source, undefined);
    assert.equal(query.q, undefined);
  }
});

test("search is trimmed and bounded to 200 Unicode characters", () => {
  assert.equal(parseJobsQuery({ q: `  ${"x".repeat(201)}  ` }).q?.length, 200);
  assert.equal(
    Array.from(parseJobsQuery({ q: "🙂".repeat(201) }).q ?? "").length,
    200,
  );
});

test("pagination preserves all committed filters and filter submission resets page", () => {
  const state = parseJobsQuery({
    page: "3",
    status: "observed",
    source,
    q: "Remote & Engineer",
  });
  const paged = new URL(
    buildJobsHref(state, { page: 4 }),
    "http://dashboard.test",
  );
  assert.equal(paged.searchParams.get("page"), "4");
  assert.equal(paged.searchParams.get("status"), "observed");
  assert.equal(paged.searchParams.get("source"), source);
  assert.equal(paged.searchParams.get("q"), "Remote & Engineer");
  const applied = new URL(
    buildJobsHref(state, { page: 1, q: "new", status: undefined }),
    "http://dashboard.test",
  );
  assert.equal(applied.searchParams.get("page"), null);
  assert.equal(applied.searchParams.get("status"), null);
  assert.equal(applied.searchParams.get("source"), source);
  assert.equal(applied.searchParams.get("q"), "new");
  assert.equal(buildJobsHref({ page: 1 }), "/dashboard/jobs");
});

test("URL building encodes search content and cannot override the dashboard path", () => {
  const href = buildJobsHref({
    page: 1,
    q: "https://other.test/?x=<script>&q=a#hash",
  });
  const url = new URL(href, "http://dashboard.test");
  assert.equal(url.origin, "http://dashboard.test");
  assert.equal(url.pathname, "/dashboard/jobs");
  assert.equal(url.hash, "");
  assert.equal(
    url.searchParams.get("q"),
    "https://other.test/?x=<script>&q=a#hash",
  );
});

test("empty states distinguish unobserved datasets, filtered empties, and out-of-range pages", () => {
  assert.equal(getJobsEmptyState(0, { page: 1 }), "unobserved");
  assert.equal(
    getJobsEmptyState(0, { page: 1, status: "observed" }),
    "filtered",
  );
  assert.equal(getJobsEmptyState(0, { page: 1, source }), "filtered");
  assert.equal(getJobsEmptyState(0, { page: 1, q: "missing" }), "filtered");
  assert.equal(getJobsEmptyState(26, { page: 3 }), "page");
  assert.equal(hasJobsFilters({ page: 2 }), false);
});
