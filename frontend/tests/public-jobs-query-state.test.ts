import assert from "node:assert/strict";
import test from "node:test";
import {
  buildPublicJobsHref,
  getPublicJobsPageCount,
  MAX_PUBLIC_JOBS_PAGE,
  needsPublicJobsNormalization,
  parsePublicJobsQuery,
  PUBLIC_JOBS_PAGE_SIZE,
} from "../lib/public-jobs/query-state";

test("query normalization trims text, keeps literal search characters, and removes invalid repeated filters", () => {
  const query = parsePublicJobsQuery({
    q: "  Backend %_\\ engineer  ",
    location: " Berlin ",
    workplace: "remote",
    employment: "full_time",
    page: "2",
  });
  assert.deepEqual(query, {
    page: 2,
    q: "Backend %_\\ engineer",
    location: "Berlin",
    workplace: "remote",
    employment: "full_time",
  });
  const invalid = parsePublicJobsQuery({
    q: ["a", "b"],
    location: "  ",
    workplace: "office",
    employment: ["contract", "other"],
    page: "-2",
  });
  assert.deepEqual(invalid, {
    page: 1,
    q: undefined,
    location: undefined,
    workplace: undefined,
    employment: undefined,
  });
});

test("Unicode text is bounded by characters without splitting surrogate pairs", () => {
  const query = parsePublicJobsQuery({
    q: "😀".repeat(201),
    location: "é".repeat(201),
  });
  assert.equal(query.q, "😀".repeat(200));
  assert.equal(query.location, "é".repeat(200));
});

test("page bounds guarantee PostgreSQL-safe offsets and reject malformed page values", () => {
  assert.ok((MAX_PUBLIC_JOBS_PAGE - 1) * PUBLIC_JOBS_PAGE_SIZE <= 2147483647);
  assert.equal(
    parsePublicJobsQuery({ page: String(MAX_PUBLIC_JOBS_PAGE) }).page,
    MAX_PUBLIC_JOBS_PAGE,
  );
  for (const page of [
    "0",
    "-1",
    "1.5",
    "NaN",
    "9007199254740992",
    String(MAX_PUBLIC_JOBS_PAGE + 1),
  ]) {
    assert.equal(parsePublicJobsQuery({ page }).page, 1);
  }
  assert.equal(parsePublicJobsQuery({ page: ["2", "3"] }).page, 1);
});

test("native form blanks and unsupported URL keys normalize to clean shareable URLs without order loops", () => {
  const empty = parsePublicJobsQuery({
    q: "",
    location: "",
    workplace: "",
    employment: "",
  });
  assert.equal(buildPublicJobsHref(empty), "/jobs");
  assert.equal(
    needsPublicJobsNormalization(
      { q: "", location: "", workplace: "", employment: "" },
      empty,
    ),
    true,
  );
  assert.equal(needsPublicJobsNormalization({}, empty), false);
  const query = parsePublicJobsQuery({
    q: "backend",
    workplace: "remote",
    page: "2",
  });
  assert.equal(
    needsPublicJobsNormalization(
      { page: "2", workplace: "remote", q: "backend" },
      query,
    ),
    false,
  );
  assert.equal(
    needsPublicJobsNormalization(
      { q: " backend ", workplace: "remote", page: "2", source: "private" },
      query,
    ),
    true,
  );
});

test("pagination links preserve all filters and filter changes reset page one", () => {
  const query = parsePublicJobsQuery({
    q: "C++ & API",
    location: "Berlin",
    workplace: "remote",
    employment: "contract",
    page: "3",
  });
  const next = new URL(
    buildPublicJobsHref(query, { page: 4 }),
    "https://frontend.test",
  );
  assert.equal(next.searchParams.get("q"), "C++ & API");
  assert.equal(next.searchParams.get("location"), "Berlin");
  assert.equal(next.searchParams.get("workplace"), "remote");
  assert.equal(next.searchParams.get("employment"), "contract");
  assert.equal(next.searchParams.get("page"), "4");
  assert.equal(
    new URL(
      buildPublicJobsHref(query, { location: "Paris" }),
      next,
    ).searchParams.has("page"),
    false,
  );
  assert.equal(
    buildPublicJobsHref(query, {
      q: undefined,
      location: undefined,
      workplace: undefined,
      employment: undefined,
    }),
    "/jobs",
  );
});

test("page count uses real totals and keeps zero results on page one", () => {
  assert.equal(getPublicJobsPageCount(0), 1);
  assert.equal(getPublicJobsPageCount(25), 1);
  assert.equal(getPublicJobsPageCount(26), 2);
  assert.equal(getPublicJobsPageCount(51), 3);
  assert.equal(
    getPublicJobsPageCount(Number.MAX_SAFE_INTEGER),
    MAX_PUBLIC_JOBS_PAGE,
  );
});
