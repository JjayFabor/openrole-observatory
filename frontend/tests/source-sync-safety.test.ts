import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";

test("actual sync components expose native idle/inactive controls, live feedback, and trustworthy result links", () => {
  const html = JSON.parse(
    execFileSync(
      process.execPath,
      ["--import", "tsx", "tests/source-sync-render-fixture.tsx"],
      { encoding: "utf8", cwd: process.cwd() },
    ),
  ) as Record<string, string>;
  assert.match(
    html.idle,
    /<button[^>]*type="button"[^>]*aria-busy="false"[^>]*>Sync now<\/button>/,
  );
  assert.doesNotMatch(html.idle, /disabled=""/);
  assert.match(html.idle, /aria-live="polite" aria-atomic="true"/);
  assert.match(html.inactive, /disabled=""/);
  assert.match(html.inactive, /aria-describedby="[^"]+"/);
  assert.match(html.inactive, /Inactive sources cannot be synchronized/);
  assert.match(html.completed, /Synchronization completed/);
  assert.match(html.completed, /Fetched 3 records/);
  assert.match(html.partial, /Completed with errors/);
  assert.match(html.partial, /Quarantined 1/);
  assert.match(
    html.partial,
    /dashboard\/quarantine\?source=11111111-1111-4111-8111-111111111111&amp;run=22222222-2222-4222-8222-222222222222/,
  );
  assert.match(
    html.completed,
    /dashboard\/runs\/22222222-2222-4222-8222-222222222222\?source=11111111-1111-4111-8111-111111111111/,
  );
  assert.match(html.failed, /Synchronization failed/);
  assert.match(html.error, /already running/);
  assert.doesNotMatch(html.error, /href=|View run/);
});
