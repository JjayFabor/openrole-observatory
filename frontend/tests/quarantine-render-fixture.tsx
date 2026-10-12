import { renderToStaticMarkup } from "react-dom/server";
import { QuarantineDetail } from "../components/quarantine/quarantine-detail";
import { QuarantineTable } from "../components/quarantine/quarantine-table";
import { SourceHealthCard } from "../components/dashboard/source-health-card";
import { quarantineDetail, quarantineRecord } from "./quarantine-fixtures";
import { sourceHealth, pipelineRun } from "./fixtures";

const unsafe =
  '<script>alert("quarantine")</script><img src=x onerror=alert(1)>';
const record = quarantineDetail({
  external_job_id: unsafe,
  raw_record_locator: unsafe,
  error_message: unsafe,
  error_code: unsafe,
  error_details: {
    markup: unsafe,
    zero: 0,
    false_value: false,
    null_value: null,
    array: [null, false, 0],
  },
});
const rendered = {
  detail: renderToStaticMarkup(<QuarantineDetail record={record} />),
  unknownIdentity: renderToStaticMarkup(
    <QuarantineDetail
      record={quarantineDetail({
        external_job_id: null,
        raw_record_locator: null,
        status: "resolved",
        resolved_at: null,
      })}
    />,
  ),
  list: renderToStaticMarkup(
    <QuarantineTable
      records={[
        quarantineRecord({ error_message: unsafe, external_job_id: unsafe }),
      ]}
    />,
  ),
  largeDetails: renderToStaticMarkup(
    <QuarantineDetail
      record={quarantineDetail({
        error_details: { message: "x".repeat(2100) },
      })}
    />,
  ),
  overviewLink: renderToStaticMarkup(
    <SourceHealthCard
      section={{
        state: "available",
        source: sourceHealth({
          latest_run: pipelineRun({ records_quarantined: 2 }),
        }),
      }}
      now={Date.parse("2026-10-09T10:02:00Z")}
    />,
  ),
  noOverviewLink: renderToStaticMarkup(
    <SourceHealthCard
      section={{
        state: "available",
        source: sourceHealth({
          latest_run: pipelineRun({ records_quarantined: 0 }),
        }),
      }}
      now={Date.parse("2026-10-09T10:02:00Z")}
    />,
  ),
};
process.stdout.write(JSON.stringify(rendered));
