import assert from "node:assert/strict";
import test from "node:test";
import {
  buildSourcesHref,
  getSourcesEmptyState,
  MAX_SOURCES_PAGE,
  parseSourcesQuery,
  SOURCES_PAGE_SIZE,
} from "../lib/sources/query-state";

test("source active/page parameters retain explicit true and false", () => {
  assert.deepEqual(parseSourcesQuery({ active: "true", page: "2" }), {
    page: 2,
    active: true,
  });
  assert.deepEqual(parseSourcesQuery({ active: "false" }), {
    page: 1,
    active: false,
  });
  assert.deepEqual(parseSourcesQuery({}), { page: 1, active: undefined });
});

test("invalid and repeated presentation parameters use safe defaults", () => {
  for (const page of [
    "0",
    "-1",
    "1.5",
    "1e3",
    "9007199254740993",
    String(MAX_SOURCES_PAGE + 1),
    ["1", "2"],
  ])
    assert.equal(parseSourcesQuery({ page }).page, 1);
  for (const active of ["yes", "TRUE", "1", ["true", "false"]])
    assert.equal(parseSourcesQuery({ active }).active, undefined);
  assert.ok((MAX_SOURCES_PAGE - 1) * SOURCES_PAGE_SIZE <= 2147483647);
});

test("pagination preserves inactive filter and changes reset page one", () => {
  assert.equal(
    buildSourcesHref({ page: 2, active: false }, { page: 3 }),
    "/dashboard/sources?active=false&page=3",
  );
  assert.equal(
    buildSourcesHref({ page: 3, active: false }, { page: 1, active: true }),
    "/dashboard/sources?active=true",
  );
  assert.equal(buildSourcesHref({ page: 1 }), "/dashboard/sources");
});

test("empty states distinguish no configured sources, filter misses and page misses", () => {
  assert.equal(getSourcesEmptyState(0, { page: 1 }), "unconfigured");
  assert.equal(getSourcesEmptyState(0, { page: 1, active: false }), "filtered");
  assert.equal(getSourcesEmptyState(26, { page: 3 }), "page");
});
