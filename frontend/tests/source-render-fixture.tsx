import { renderToStaticMarkup } from "react-dom/server";
import { SourceDetail } from "../components/sources/source-detail";
import { SourceTable } from "../components/sources/source-table";
import { sourceRead } from "./source-fixtures";
import { pipelineRun } from "./fixtures";
import { QuarantineDetail } from "../components/quarantine/quarantine-detail";
import { quarantineDetail } from "./quarantine-fixtures";
import { JobsTable } from "../components/jobs/jobs-table";
import { SourceHealthCard } from "../components/dashboard/source-health-card";
import type { JobListItem } from "../lib/api/types";

const unsafe = '<script>alert("source")</script><img src=x onerror=alert(1)>';
const source = sourceRead({
  company: {
    ...sourceRead().company,
    name: unsafe,
    domain: unsafe,
    careers_url: "javascript:alert(1)",
  },
  latest_run: pipelineRun({
    status: "failed",
    error_code: "SOURCE_TIMEOUT",
    error_summary: "The provider request timed out.",
  }),
  last_successful_sync_at: "2026-10-08T10:00:00Z",
});
const now = Date.parse("2026-10-09T10:02:00Z");
const jobs: JobListItem[] = [
  {
    id: source.id,
    external_job_id: "123",
    company: { id: source.company.id, name: "Example" },
    source: { id: source.id, provider: source.provider },
    lifecycle_status: "observed",
    first_seen_at: "2026-10-09T10:00:00Z",
    last_seen_at: "2026-10-09T10:00:00Z",
    absence_first_detected_at: null,
    reappeared_at: null,
    consecutive_absent_runs: 0,
    current_version: {
      id: source.id,
      version_number: 1,
      title: "Engineer",
      location_text: null,
      workplace_type: null,
      employment_type: null,
    },
  },
];
const rendered = {
  detail: renderToStaticMarkup(
    <SourceDetail
      source={source}
      runs={{ state: "unavailable" }}
      quarantine={{ state: "available", records: [] }}
      now={now}
    />,
  ),
  safeLink: renderToStaticMarkup(
    <SourceDetail
      source={sourceRead()}
      runs={{ state: "available", runs: [] }}
      quarantine={{ state: "available", records: [] }}
      now={now}
    />,
  ),
  never: renderToStaticMarkup(
    <SourceDetail
      source={sourceRead({
        last_attempted_sync_at: null,
        last_successful_sync_at: null,
        latest_run: null,
      })}
      runs={{ state: "available", runs: [] }}
      quarantine={{ state: "available", records: [] }}
      now={now}
    />,
  ),
  list: renderToStaticMarkup(<SourceTable sources={[source]} />),
  quarantine: renderToStaticMarkup(
    <QuarantineDetail record={quarantineDetail()} />,
  ),
  jobs: renderToStaticMarkup(<JobsTable jobs={jobs} />),
  overview: renderToStaticMarkup(
    <SourceHealthCard section={{ state: "available", source }} now={now} />,
  ),
};
process.stdout.write(JSON.stringify(rendered));
