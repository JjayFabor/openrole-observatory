import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";
import { sourceId } from "./fixtures";
import { quarantineSourceId } from "./quarantine-fixtures";

test("source components escape text, separate active/run facts, and preserve safe related navigation", () => {
  const rendered = JSON.parse(
    execFileSync(
      process.execPath,
      ["--import", "tsx", "tests/source-render-fixture.tsx"],
      { encoding: "utf8", cwd: process.cwd() },
    ),
  ) as Record<string, string>;
  for (const html of [rendered.detail, rendered.list]) {
    assert.doesNotMatch(html, /<script>|<img src=x|href="javascript:/);
    assert.match(html, /&lt;script&gt;/);
  }
  assert.match(rendered.detail, />Active<\/span>/);
  assert.match(rendered.detail, />Failed<\/span>/);
  assert.match(rendered.detail, /Latest synchronization failed/);
  assert.match(rendered.detail, /Oct 8, 2026, 10:00:00 UTC/);
  assert.match(rendered.detail, /Unable to load recent pipeline runs/);
  assert.match(rendered.detail, /No recent quarantined records/);
  assert.match(rendered.never, /Never synchronized/);
  assert.match(rendered.never, /No runs yet/);
  assert.doesNotMatch(
    rendered.never,
    /Latest synchronization failed|Invalid Date/,
  );
  assert.match(
    rendered.safeLink,
    /href="https:\/\/example.test\/careers" target="_blank" rel="noopener noreferrer"/,
  );
  for (const path of [
    `/dashboard/jobs?source=${sourceId}`,
    `/dashboard/runs?source=${sourceId}`,
    `/dashboard/quarantine?source=${sourceId}`,
  ])
    assert.ok(rendered.detail.includes(`href="${path}"`));
  assert.ok(rendered.jobs.includes(`href="/dashboard/sources/${sourceId}"`));
  assert.ok(
    rendered.overview.includes(`href="/dashboard/sources/${sourceId}"`),
  );
  assert.ok(
    rendered.quarantine.includes(
      `href="/dashboard/sources/${quarantineSourceId}"`,
    ),
  );
  assert.doesNotMatch(
    rendered.detail,
    /configuration|credentials|external_account_key|Sync now|Test connection|Create source|Edit source/,
  );
});
