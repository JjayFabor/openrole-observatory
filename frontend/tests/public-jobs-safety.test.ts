import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";

type Fixture = {
  populated: string;
  middle: string;
  last: string;
  empty: string;
  filtered: string;
  changingPage: string;
  failure: string;
  detail: string;
  historicalDetail: string;
  detailFailure: string;
  loading: string;
  detailLoading: string;
  missing: string;
  boundary: string;
  maximum: string;
  clamp: { digest: string; requests: number };
  zeroClamp: { digest: string; requests: number };
  normalization: { digest: string; requests: number };
};
const rendered: Fixture = JSON.parse(
  execFileSync(
    process.execPath,
    ["--import", "tsx", "tests/public-jobs-render-fixture.tsx"],
    { cwd: process.cwd(), encoding: "utf8" },
  ),
);

test("actual discovery renders escaped source text, public title links, and prominent UTC source evidence", () => {
  assert.match(
    rendered.populated,
    /&lt;img src=x onerror=attack\(\)&gt;Backend Engineer/,
  );
  assert.match(
    rendered.populated,
    /&lt;script&gt;companyAttack\(\)&lt;\/script&gt;/,
  );
  assert.match(
    rendered.populated,
    /href="\/jobs\/33333333-3333-4333-8333-333333333333"/,
  );
  assert.match(
    rendered.populated,
    /<time dateTime="2026-10-12T00:00:00Z"[^>]*>Oct 12, 2026, 00:00:00 UTC<\/time>/,
  );
  assert.match(rendered.populated, /Last observed/);
  assert.match(rendered.populated, /Direct source · Greenhouse/);
  assert.match(rendered.populated, /Remote · Full-time/);
  assert.match(rendered.populated, /USD 90,000 – 110,000 \/ year/);
  assert.match(rendered.populated, /Location not stated/);
  assert.match(rendered.populated, /overflow-wrap:anywhere/);
  assert.doesNotMatch(
    rendered.populated,
    /<script|privateDescription|private-run-id|private-token|unknown_workplace|unknown_employment|\/dashboard|Apply|Save|Salary: —/,
  );
  const content = rendered.populated.match(/<main\b[^>]*>([\s\S]*?)<\/main>/)?.[1];
  assert.ok(content);
  assert.doesNotMatch(content, /<img\b/);
});

test("GET filters use URL values rather than restored drafts, include supported choices, and reset pagination on submit", () => {
  assert.match(
    rendered.populated,
    /<form\b[^>]*action="\/jobs"[^>]*method="get"/,
  );
  assert.match(rendered.populated, /<form\b[^>]*autoComplete="off"/);
  for (const name of ["q", "location", "workplace", "employment"])
    assert.match(rendered.populated, new RegExp(`name="${name}"`));
  assert.match(rendered.populated, /htmlFor="jobs-search"|for="jobs-search"/);
  assert.match(rendered.populated, /name="q"[^>]*value="backend"/);
  assert.match(rendered.populated, /<option value="remote" selected=""/);
  assert.match(rendered.populated, /<option value="full_time" selected=""/);
  for (const value of [
    "part_time",
    "contract",
    "temporary",
    "internship",
    "volunteer",
    "other",
    "hybrid",
    "onsite",
  ])
    assert.match(rendered.populated, new RegExp(`<option value="${value}"`));
  assert.match(rendered.populated, /type="submit"[^>]*>Search<\/button>/);
  assert.doesNotMatch(
    rendered.populated,
    /name="page"|name="source"|name="status"|<table/,
  );
});

test("pagination uses the real total, preserves filters, and communicates disabled boundaries", () => {
  assert.match(rendered.populated, /51 jobs found/);
  assert.match(rendered.populated, /Page 1 of 3/);
  assert.match(rendered.populated, /aria-disabled="true"[^>]*>Previous/);
  assert.match(
    rendered.populated,
    /href="\/jobs\?q=backend&amp;workplace=remote&amp;employment=full_time&amp;page=2"/,
  );
  assert.match(rendered.middle, /Page 2 of 3/);
  assert.match(
    rendered.middle,
    /href="\/jobs\?q=backend&amp;workplace=remote"[^>]*>Previous/,
  );
  assert.match(rendered.last, /Page 3 of 3/);
  assert.match(rendered.last, /aria-disabled="true"[^>]*>Next/);
  assert.match(rendered.maximum, /aria-disabled="true"[^>]*>Next/);
});

test("empty dataset, filtered empty results, and a changing in-range page remain distinct", () => {
  assert.match(rendered.empty, /No listings are available yet/);
  assert.match(rendered.filtered, /No jobs match these filters/);
  assert.match(rendered.filtered, /href="\/jobs"[^>]*>Clear filters/);
  assert.match(rendered.changingPage, /No jobs on this page/);
  assert.match(rendered.changingPage, /40 jobs found/);
  assert.match(
    rendered.changingPage,
    /href="\/jobs\?q=backend"[^>]*>Go to first page/,
  );
});

test("normalization redirects before fetching and out-of-range redirects use totals", () => {
  assert.match(
    rendered.normalization.digest,
    /;\/jobs\?q=backend&workplace=remote;/,
  );
  assert.equal(rendered.normalization.requests, 0);
  assert.match(rendered.clamp.digest, /;\/jobs\?q=backend&page=2;/);
  assert.equal(rendered.clamp.requests, 1);
  assert.match(rendered.zeroClamp.digest, /;\/jobs\?q=missing;/);
});

test("public failures preserve filters and use full-request retry without exposing backend details", () => {
  assert.match(rendered.failure, /couldn’t load jobs right now/);
  assert.match(rendered.failure, /name="q"[^>]*value="backend"/);
  assert.match(
    rendered.failure,
    /href="\/jobs\?q=backend&amp;workplace=remote"[^>]*>Try again/,
  );
  for (const markup of [
    rendered.failure,
    rendered.boundary,
    rendered.detailFailure,
  ])
    assert.doesNotMatch(
      markup,
      /postgres|PRIVATE_|private-token|stack trace|0 jobs found|No jobs match|FastAPI/i,
    );
});

test("discovery links into real public detail with safe historical, loading, and missing states", () => {
  assert.match(
    rendered.detail,
    /&lt;script&gt;titleAttack\(\)&lt;\/script&gt;/,
  );
  assert.match(rendered.detail, /Example Employer/);
  assert.match(rendered.detail, /Description/);
  assert.match(rendered.detail, /View original listing/);
  assert.match(rendered.historicalDetail, /Backend Engineer/);
  assert.doesNotMatch(
    rendered.detail,
    /privateDescription|<script|source_url|Task 46|\/dashboard/,
  );
  assert.match(rendered.missing, /Job not found/);
  assert.match(rendered.missing, /href="\/jobs"/);
  for (const markup of [rendered.loading, rendered.detailLoading]) {
    assert.match(markup, /aria-busy="true"/);
    assert.match(markup, /role="status"/);
    assert.doesNotMatch(markup, /Example Employer|Backend Engineer/);
  }
  for (const markup of [
    rendered.populated,
    rendered.detail,
    rendered.missing,
    rendered.loading,
    rendered.boundary,
  ]) {
    assert.equal([...markup.matchAll(/<main\b/g)].length, 1);
    assert.equal([...markup.matchAll(/<h1\b/g)].length, 1);
  }
});
