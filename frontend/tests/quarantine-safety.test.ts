import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";

test("actual quarantine components escape source/debug text and preserve conservative identity/provenance", () => {
  // ReactDOMServer uses the normal React export; API tests use the server-only condition.
  const output = execFileSync(
    process.execPath,
    ["--import", "tsx", "tests/quarantine-render-fixture.tsx"],
    { encoding: "utf8", cwd: process.cwd() },
  );
  const rendered = JSON.parse(output) as Record<string, string>;
  for (const html of [rendered.detail, rendered.list]) {
    assert.doesNotMatch(html, /<script>|<img src=x/);
    assert.match(html, /&lt;script&gt;/);
  }
  assert.match(rendered.detail, /&quot;zero&quot;: 0/);
  assert.match(rendered.detail, /&quot;false_value&quot;: false/);
  assert.match(rendered.detail, /&quot;null_value&quot;: null/);
  assert.match(
    rendered.detail,
    /<pre role="region" tabindex="0" aria-label="Structured error details JSON"/,
  );
  assert.match(
    rendered.detail,
    /<aside aria-labelledby="lifecycle-safety-note"/,
  );
  assert.match(
    rendered.detail,
    /<h2 id="lifecycle-safety-note"[^>]*>Lifecycle Safety Note<\/h2>/,
  );
  assert.match(
    rendered.unknownIdentity,
    /No external job ID could be recovered/,
  );
  assert.match(
    rendered.unknownIdentity,
    /can prevent safe absence reconciliation/,
  );
  assert.match(
    rendered.unknownIdentity,
    /does not establish that the entire pipeline run failed/,
  );
  assert.match(
    rendered.detail,
    /href="\/dashboard\/runs\/22222222-2222-4222-8222-222222222222\?source=33333333-3333-4333-8333-333333333333"/,
  );
  assert.match(rendered.largeDetails, /<details>/);
  assert.doesNotMatch(
    rendered.detail,
    /<button[^>]*>Resolve|<button[^>]*>Retry|dangerouslySetInnerHTML/,
  );
  assert.match(
    rendered.overviewLink,
    /href="\/dashboard\/quarantine\?run=22222222-2222-4222-8222-222222222222"/,
  );
  assert.doesNotMatch(rendered.noOverviewLink, /View quarantined records/);
});
