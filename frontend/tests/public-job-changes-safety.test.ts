import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";

type Fixture = {
  populated: string;
  empty: string;
  failure: string;
  missingSecondary: string;
  malformedSecondary: string;
  page: string;
  pageRequests: string[];
  metadata: { title: string };
  metadataRequests: string[];
  primaryFailure: string;
  primaryFailureRequests: string[];
  loading: string;
};
const rendered: Fixture = JSON.parse(
  execFileSync(
    process.execPath,
    ["--import", "tsx", "tests/public-job-changes-render-fixture.tsx"],
    { cwd: process.cwd(), encoding: "utf8" },
  ),
);

test("actual section renders separate newest observation groups with explicit accessible before/after values", () => {
  assert.match(rendered.populated, /Recent listing changes/);
  assert.equal([...rendered.populated.matchAll(/<h3\b/g)].length, 3);
  assert.equal(
    [...rendered.populated.matchAll(/Oct 12, 2026, 00:00 UTC/g)].length,
    2,
  );
  assert.match(rendered.populated, /Before/);
  assert.match(rendered.populated, /After/);
  assert.match(rendered.populated, /Remote/);
  assert.match(rendered.populated, /Hybrid/);
  assert.match(rendered.populated, /Location removed/);
  assert.match(rendered.populated, /Not stated/);
  assert.match(rendered.populated, /Unavailable/);
  assert.match(rendered.populated, /overflow-wrap:anywhere/);
  assert.doesNotMatch(
    rendered.populated,
    /future_workplace|Changed by employer|Page \d|hasMore/,
  );
});

test("historical text is escaped, salary is semantic and exact, description changes never render bodies", () => {
  assert.match(
    rendered.populated,
    /&lt;img src=x onerror=attack\(\)&gt;Engineer/,
  );
  assert.match(rendered.populated, /USD 0 – 9,007,199,254,740,993\.01 \/ year/);
  assert.match(
    rendered.populated,
    /Amount not stated · Currency: USD · Period: year/,
  );
  assert.match(
    rendered.populated,
    /Amount not stated · Currency: EUR · Period: month/,
  );
  for (const marker of [
    "Description updated",
    "Description added",
    "Description removed",
  ])
    assert.match(rendered.populated, new RegExp(marker));
  assert.doesNotMatch(
    rendered.populated,
    /<script|private-old|private-new|private-run|private-version|private-hash|private-metadata|version_number|canonical_metadata|source_url|Salary minimum|\/dashboard/,
  );
  const content = rendered.populated.match(/<main\b[^>]*>([\s\S]*?)<\/main>/)?.[1];
  assert.ok(content);
  assert.doesNotMatch(content, /<img\b/);
});

test("successful empty history differs from secondary failure and missing history", () => {
  assert.match(rendered.empty, /No material listing changes recorded/);
  for (const markup of [
    rendered.failure,
    rendered.missingSecondary,
    rendered.malformedSecondary,
  ]) {
    assert.match(markup, /Change history is unavailable right now/);
    assert.doesNotMatch(
      markup,
      /No material listing changes recorded|Job not found|private-token|postgres|PRIVATE_|private-metadata/,
    );
  }
  assert.match(rendered.failure, /Backend Engineer/);
  assert.match(rendered.failure, /View original listing/);
  assert.match(rendered.failure, /Description/);
});

test("page integrates an independent history loading boundary after current detail", () => {
  assert.match(rendered.page, /Backend Engineer/);
  assert.match(rendered.page, /View original listing/);
  assert.match(rendered.page, /Loading recent changes/);
  assert.ok(
    rendered.page.indexOf("Description</h2>") <
      rendered.page.indexOf("Recent listing changes"),
  );
  assert.ok(rendered.pageRequests.some((path) => path.endsWith("/changes")));
  assert.match(rendered.loading, /aria-busy="true"/);
  assert.match(rendered.loading, /role="status"/);
  assert.doesNotMatch(
    rendered.loading,
    /Backend Engineer|Oct \d|No material listing changes recorded/,
  );
});

test("history stays out of metadata and never fetches when primary detail is unavailable", () => {
  assert.equal(rendered.metadata.title, "Backend Engineer at Example Employer");
  assert.equal(rendered.metadataRequests.length, 1);
  assert.ok(
    rendered.metadataRequests.every((path) => !path.endsWith("/changes")),
  );
  assert.match(rendered.primaryFailure, /couldn’t load this job/);
  assert.ok(
    rendered.primaryFailureRequests.every((path) => !path.endsWith("/changes")),
  );
  assert.doesNotMatch(rendered.primaryFailure, /Recent listing changes/);
});
