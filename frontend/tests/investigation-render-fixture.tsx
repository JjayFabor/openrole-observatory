import Module, { createRequire } from "node:module";
import { renderToStaticMarkup } from "react-dom/server";
import { RunDetail } from "../components/runs/run-detail";
import { RunsTable } from "../components/runs/runs-table";
import { RecentRuns } from "../components/dashboard/recent-runs";
import { QuarantineDetail } from "../components/quarantine/quarantine-detail";
import {
  jobChange,
  jobDetailFixture,
  jobLifecycle,
} from "./job-detail-fixtures";
import { sourceRead } from "./source-fixtures";
import { pipelineRun } from "./fixtures";
import { quarantineDetail } from "./quarantine-fixtures";

async function render() {
  // Only this Node rendering fixture bypasses the bundler sentinel; production keeps its server-only boundary.
  const require = createRequire(import.meta.url);
  const serverOnly = require.resolve("server-only");
  const sentinel = new Module(serverOnly);
  sentinel.exports = {};
  sentinel.loaded = true;
  require.cache[serverOnly] = sentinel;
  const { JobDetail } = await import("../components/jobs/job-detail");
  const detail = jobDetailFixture();
  detail.job.current_version.description =
    '<h1>Safe description</h1><p onclick="attack()">Build pipelines.</p><script>attack()</script><img src=x onerror=attack()><a href="javascript:attack()">Unsafe URL</a>';
  detail.job.current_version.title =
    "<img src=x onerror=attack()>Backend Engineer";
  detail.job.current_version.location_text = "L".repeat(400);
  detail.job.current_version.canonical_metadata = {
    html: "<script>debug()</script>",
    false: false,
    zero: 0,
    nested: null,
  };
  detail.changes = {
    state: "available",
    data: {
      items: [
        jobChange({ new_value: "future_workplace<script>" }),
        jobChange({
          id: "99999999-9999-4999-8999-999999999999",
          field_name: "canonical_metadata",
          old_value: false,
          new_value: { zero: 0 },
        }),
        jobChange({
          id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          field_name: "source_url",
          old_value: "https://example.test/jobs/123",
          new_value: `https://example.test/${"long-url-token".repeat(300)}?text=<script>&scope=source`,
        }),
      ],
      hasNext: false,
    },
  };
  const run = pipelineRun({
    status: "completed_with_errors",
    records_fetched: 0,
    jobs_new: 0,
    error_code: "<script>code()</script>",
    error_summary: "<img src=x onerror=attack()>",
  });
  const runDetail = {
    state: "available" as const,
    run,
    source: { state: "available" as const, data: sourceRead() },
  };
  const failed = pipelineRun({
    status: "failed",
    error_summary: "Source request failed.",
    records_fetched: 0,
    records_valid: 0,
    records_quarantined: 0,
    jobs_new: 0,
    jobs_changed: 0,
    jobs_unchanged: 0,
  });
  const query = { versions: 1, changes: 1, lifecycle: 1 };
  process.stdout.write(
    JSON.stringify({
      job: renderToStaticMarkup(<JobDetail detail={detail} query={query} />),
      tentativeJob: renderToStaticMarkup(
        <JobDetail
          detail={{
            ...detail,
            job: {
              ...detail.job,
              consecutive_absent_runs: 1,
              absence_first_detected_at: "2026-10-09T10:00:00Z",
              no_longer_observed_at: null,
              reappeared_at: null,
            },
            source: {
              state: "available",
              data: sourceRead({
                last_attempted_sync_at: "2026-10-10T10:00:00Z",
                last_successful_sync_at: "2026-10-10T10:01:00Z",
                latest_run: pipelineRun({
                  status: "completed_with_errors",
                  started_at: "2026-10-10T10:00:00Z",
                  completed_at: "2026-10-10T10:01:00Z",
                }),
              }),
            },
            lifecycle: {
              state: "available",
              data: {
                summary: jobLifecycle({
                  current_status: "observed",
                  consecutive_absent_runs: 1,
                  absence_first_detected_at: "2026-10-09T10:00:00Z",
                  no_longer_observed_at: null,
                  reappeared_at: null,
                  events: [],
                }),
                hasNext: false,
              },
            },
          }}
          query={query}
        />,
      ),
      partialJob: renderToStaticMarkup(
        <JobDetail
          detail={{
            ...detail,
            source: { state: "unavailable" },
            versions: { state: "unavailable" },
            changes: { state: "unavailable" },
            lifecycle: { state: "unavailable" },
          }}
          query={query}
        />,
      ),
      run: renderToStaticMarkup(<RunDetail detail={runDetail} />),
      failed: renderToStaticMarkup(
        <RunDetail
          detail={{
            state: "available",
            run: failed,
            source: { state: "unavailable" },
          }}
        />,
      ),
      runs: renderToStaticMarkup(<RunsTable runs={[run]} />),
      recent: renderToStaticMarkup(
        <RecentRuns
          section={{ state: "available", runs: [run] }}
          now={Date.parse(run.started_at)}
        />,
      ),
      quarantine: renderToStaticMarkup(
        <QuarantineDetail record={quarantineDetail()} />,
      ),
    }),
  );
}
void render();
