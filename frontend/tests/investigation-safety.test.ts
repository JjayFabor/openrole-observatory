import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";
import { pipelineRun } from "./fixtures";
import { quarantineRunId, quarantineSourceId } from "./quarantine-fixtures";
test("actual investigation components sanitize descriptions and retain escaped historical/debug facts", () => {
  const html = JSON.parse(
    execFileSync(
      process.execPath,
      ["--import", "tsx", "tests/investigation-render-fixture.tsx"],
      { encoding: "utf8", cwd: process.cwd() },
    ),
  ) as Record<string, string>;
  assert.doesNotMatch(html.job, /<script>|<img |href="javascript:|<p onclick=/);
  assert.match(html.job, /<h3>Safe description<\/h3>/);
  assert.match(html.job, /future_workplace&lt;script&gt;/);
  const longUrl = `https://example.test/${"long-url-token".repeat(300)}`;
  assert.ok(
    html.job.includes(`${longUrl}?text=&lt;script&gt;&amp;scope=source`),
  );
  assert.ok(!html.job.includes(`href="${longUrl}`));
  assert.match(html.job, /Not observed → Observed/);
  assert.match(html.job, /Consecutive absent runs/);
  assert.match(html.job, /&quot;zero&quot;: 0/);
  assert.match(html.job, /&quot;false&quot;: false/);
  assert.match(
    html.job,
    /role="region" aria-label="Current canonical metadata" tabindex="0"/,
  );
  assert.match(html.job, /Current JobVersion ID/);
  assert.doesNotMatch(html.job, /Employer changed|Employer closed/);
  assert.match(
    html.tentativeJob,
    /Absence detected; awaiting confirmation\. Status remains Observed\./,
  );
  assert.doesNotMatch(html.tentativeJob, /latest successful source check/);
  assert.match(html.partialJob, /Build pipelines/);
  for (const message of [
    "Unable to load source summary",
    "Unable to load version history",
    "Unable to load change history",
    "Unable to load lifecycle history",
  ])
    assert.ok(html.partialJob.includes(message));
  assert.match(html.run, /Synchronization completed with record errors/);
  assert.match(html.run, /2 records were quarantined/);
  assert.doesNotMatch(html.run, /<script>|<img |Failure Information/);
  assert.match(html.run, /&lt;script&gt;code/);
  assert.match(html.run, /Records fetched<\/dt><dd[^>]*>0<\/dd>/);
  assert.match(html.failed, /Failure Information/);
  assert.match(html.failed, /Source request failed/);
  assert.match(html.failed, /Run facts remain available/);
  const run = pipelineRun();
  for (const key of ["run", "runs", "recent"])
    assert.ok(
      html[key].includes(
        `href="/dashboard/sources/${run.source_connection_id}"`,
      ),
    );
  assert.equal(
    html.recent.split(
      `href="/dashboard/runs/${run.id}?source=${run.source_connection_id}"`,
    ).length - 1,
    2,
  );
  assert.ok(html.recent.includes('href="/dashboard/runs"'));
  assert.match(
    html.recent,
    /role="region" aria-label="Recent pipeline runs table, scroll horizontally for metrics" tabindex="0"/,
  );
  assert.ok(
    html.quarantine.includes(
      `href="/dashboard/runs/${quarantineRunId}?source=${quarantineSourceId}"`,
    ),
  );
});
