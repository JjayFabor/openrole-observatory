import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";

type Fixture = {
  observed: string;
  sparse: string;
  absent: string;
  reappeared: string;
  tentative: string;
  partialSalary: string;
  plain: string;
  encoded: string;
  dashboardEncoded: string;
  emptyDescriptions: string[];
  dashboardEmpty: string;
  dashboardHeadings: string;
  unsafeComponentLinks: string[];
  httpSource: string;
  metadata: { title: string; description: string };
  missingMetadata: string;
  malformedMetadata: string;
  missingPage: string;
  availableLayout: string;
  missingLayout: string;
  malformedLayout: string;
  unavailableLayout: string;
  failure: string;
  unavailableMetadata: { title: string; description: string };
  unsafeApi: string;
  loading: string;
  missing: string;
  boundary: string;
};
const rendered: Fixture = JSON.parse(
  execFileSync(
    process.execPath,
    ["--import", "tsx", "tests/public-job-detail-render-fixture.tsx"],
    { cwd: process.cwd(), encoding: "utf8" },
  ),
);

test("public and dashboard descriptions render encoded markup after sanitization", () => {
  for (const markup of [rendered.encoded, rendered.dashboardEncoded]) {
    assert.match(
      markup,
      /<div><div>Employer introduction\.<\/div><div>Build safe <strong>systems<\/strong>\.<\/div><\/div>/,
    );
    assert.match(markup, /<h3>Responsibilities<\/h3>/);
    assert.match(markup, /<ul><li>Help people<\/li><\/ul>/);
    assert.doesNotMatch(
      markup,
      /&lt;div|&lt;h2|&lt;ul|<script|privateScript|href="javascript:|whitespace-pre-line/,
    );
  }
});

test("actual public detail exposes escaped listing facts, observation dates, and the safe original-source action", () => {
  assert.match(
    rendered.observed,
    /Backend &lt;img src=x onerror=attack\(\)&gt; Engineer/,
  );
  assert.match(
    rendered.observed,
    /Employer &lt;script&gt;nameAttack\(\)&lt;\/script&gt;/,
  );
  assert.match(rendered.observed, /First observed/);
  assert.match(rendered.observed, /Last observed/);
  assert.match(rendered.observed, /Oct 12, 2026, 00:00:00 UTC/);
  assert.match(rendered.observed, /Direct source · Greenhouse/);
  assert.match(
    rendered.observed,
    /href="https:\/\/boards.greenhouse.io\/example\/jobs\/123" target="_blank" rel="noopener noreferrer"/,
  );
  assert.match(rendered.observed, /View original listing/);
  assert.match(rendered.observed, /Opens in a new tab/);
  assert.match(rendered.observed, /overflow-wrap:anywhere/);
  assert.doesNotMatch(
    rendered.observed,
    /href="javascript:|private-run-id|private-hash|consecutive_absent_runs|33333333|\/dashboard|Posted|Updated|Apply|Save/,
  );
});

test("not-observed and reappeared states express current facts without employer-closure claims", () => {
  assert.match(rendered.absent, /Not currently observed/);
  assert.match(rendered.absent, /no longer currently observed at its source/);
  assert.match(rendered.absent, /Absence confirmed/);
  assert.match(rendered.absent, /Check original source/);
  assert.doesNotMatch(
    rendered.absent,
    /Closed|Expired|Removed|Inactive|View original listing/,
  );
  assert.match(rendered.reappeared, /Previously not observed · Reappeared/);
  assert.match(rendered.reappeared, /View original listing/);
  assert.doesNotMatch(
    rendered.reappeared,
    /Absence confirmed|no longer currently observed/,
  );
  assert.match(rendered.tentative, /View original listing/);
  assert.doesNotMatch(
    rendered.tentative,
    /Not currently observed|Absence confirmed|no longer currently observed/,
  );
});

test("shared description rendering keeps readable safe formatting and normalizes every source heading", () => {
  for (const markup of [rendered.observed, rendered.dashboardHeadings]) {
    assert.match(markup, /<h3>About this role<\/h3>/);
    assert.match(markup, /<h3>Responsibilities<\/h3>/);
    assert.match(markup, /Safe <strong>work<\/strong>/);
    assert.match(markup, /<ul><li>Build systems<\/li><\/ul>/);
    assert.match(
      markup,
      /href="https:\/\/example.test\/details" target="_blank" rel="noopener noreferrer"/,
    );
    assert.doesNotMatch(
      markup,
      /<script|<iframe|onclick=|style="position|href="javascript:|privateScript|<h[456]/,
    );
    const content = markup.match(/<main\b[^>]*>([\s\S]*?)<\/main>/)?.[1] ?? markup;
    assert.doesNotMatch(content, /<img\b/);
  }
  assert.match(rendered.plain, /whitespace-pre-line/);
  assert.match(
    rendered.plain,
    /First line\nSecond line\nSalary &lt; 100000 &amp; benefits/,
  );
  for (const markup of rendered.emptyDescriptions) {
    assert.match(markup, /No description is available/);
    assert.doesNotMatch(markup, /<script|privateScript|>—</);
  }
  assert.match(rendered.dashboardEmpty, />—<\/p>/);
});

test("sparse details omit unknown fields while partial salary retains explicit amounts and unavailable units", () => {
  assert.match(rendered.sparse, /Location not stated/);
  assert.match(rendered.sparse, /No description is available/);
  assert.doesNotMatch(
    rendered.sparse,
    /unknown_workplace|Workplace<\/dt>|Employment type<\/dt>|>—<|Salary:|USD/,
  );
  assert.match(
    rendered.partialSalary,
    /0\+ \(currency unavailable; period unavailable\)/,
  );
});

test("component source safety blocks unsafe links while the API boundary remains strict", () => {
  for (const markup of rendered.unsafeComponentLinks) {
    assert.doesNotMatch(
      markup,
      /View original listing|href="(?:javascript:|https:\/\/user:|\/\/example)/,
    );
  }
  assert.match(rendered.httpSource, /href="http:\/\/example.test\/jobs\/123"/);
  assert.match(rendered.unsafeApi, /couldn’t load this job/);
  assert.doesNotMatch(
    rendered.unsafeApi,
    /href="javascript:|View original listing/,
  );
});

test("route metadata uses real public fields; missing identities throw not-found while outages remain unavailable", () => {
  assert.equal(rendered.metadata.title, "Backend Engineer at Example Employer");
  assert.match(rendered.metadata.description, /Last observed.*UTC/);
  for (const digest of [
    rendered.missingMetadata,
    rendered.malformedMetadata,
    rendered.missingPage,
    rendered.missingLayout,
    rendered.malformedLayout,
  ]) {
    assert.match(digest, /NEXT_HTTP_ERROR_FALLBACK;404/);
  }
  assert.equal(rendered.unavailableMetadata.title, "Job unavailable");
  assert.doesNotMatch(
    JSON.stringify(rendered.unavailableMetadata),
    /PRIVATE_|private-token|postgres|not found/i,
  );
});

test("detail layout preserves available or unavailable children while guarding missing resources", () => {
  assert.match(rendered.availableLayout, /Existing listing content/);
  assert.match(rendered.unavailableLayout, /Public unavailable feedback/);
  assert.doesNotMatch(rendered.unavailableLayout, /Job not found/);
  assert.match(rendered.missingLayout, /NEXT_HTTP_ERROR_FALLBACK;404/);
});

test("public loading, missing and failures retain landmarks and disclose no technical diagnostics", () => {
  assert.match(rendered.loading, /aria-busy="true"/);
  assert.match(rendered.loading, /role="status"/);
  assert.match(rendered.missing, /Job not found/);
  assert.match(rendered.missing, /href="\/jobs"/);
  for (const markup of [rendered.failure, rendered.boundary]) {
    assert.match(markup, /couldn’t load this job/);
    assert.doesNotMatch(
      markup,
      /PRIVATE_|private-token|postgres|stack trace|FastAPI|APIError|Job not found/,
    );
  }
  for (const markup of [
    rendered.observed,
    rendered.absent,
    rendered.loading,
    rendered.missing,
    rendered.failure,
    rendered.boundary,
  ]) {
    assert.equal([...markup.matchAll(/<h1\b/g)].length, 1);
    assert.equal([...markup.matchAll(/<main\b/g)].length, 1);
  }
});
