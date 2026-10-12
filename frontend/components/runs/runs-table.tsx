import Link from "next/link";
import type { PipelineRun } from "@/lib/api/types";
import { PipelineStatusBadge } from "@/components/dashboard/pipeline-status-badge";
import {
  formatAbsoluteTimestamp,
  formatRunDuration,
} from "@/lib/dashboard/presentation";
import { buildQuarantineHref } from "@/lib/quarantine/query-state";

const linkClass =
  "text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring";
export function RunsTable({ runs }: { runs: PipelineRun[] }) {
  return (
    <div
      role="region"
      aria-label="Pipeline runs table, scroll horizontally for metrics"
      tabIndex={0}
      className="overflow-x-auto rounded-lg border border-border bg-card outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <table className="w-full min-w-[1380px] table-fixed text-left text-xs">
        <caption className="sr-only">
          Persisted pipeline runs ordered newest first, including source,
          timestamps, duration, and record/job metrics.
        </caption>
        <thead className="border-b border-border bg-muted/40">
          <tr>
            {[
              "Status",
              "Source",
              "Started",
              "Duration",
              "Fetched",
              "Valid",
              "New",
              "Changed",
              "Unchanged",
              "Quarantined",
            ].map((label, index) => (
              <th
                key={label}
                scope="col"
                className={`px-4 py-3 font-medium text-muted-foreground ${index === 0 ? "w-[210px]" : index === 1 ? "w-[250px]" : index === 2 ? "w-[220px]" : "w-[100px]"} ${index >= 4 ? "text-right" : ""}`}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-t border-border align-top">
              <td className="px-4 py-4">
                <Link
                  href={`/dashboard/runs/${run.id}?source=${run.source_connection_id}`}
                  prefetch={false}
                  aria-label={`Pipeline run ${run.id}`}
                  className="rounded outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <PipelineStatusBadge status={run.status} />
                </Link>
                {run.error_code && (
                  <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                    {run.error_code}
                  </p>
                )}
              </td>
              <td className="px-4 py-4">
                <Link
                  href={`/dashboard/sources/${run.source_connection_id}`}
                  prefetch={false}
                  className={`break-all font-mono leading-5 ${linkClass}`}
                >
                  {run.source_connection_id}
                </Link>
              </td>
              <td className="px-4 py-4">
                <time dateTime={run.started_at} className="leading-5">
                  {formatAbsoluteTimestamp(run.started_at)}
                </time>
              </td>
              <td className="px-4 py-4 tabular-nums">
                {formatRunDuration(run)}
              </td>
              {[
                run.records_fetched,
                run.records_valid,
                run.jobs_new,
                run.jobs_changed,
                run.jobs_unchanged,
              ].map((value, index) => (
                <td key={index} className="px-4 py-4 text-right tabular-nums">
                  {value.toLocaleString("en-US")}
                </td>
              ))}
              <td className="px-4 py-4 text-right tabular-nums">
                {run.records_quarantined > 0 ? (
                  <Link
                    href={buildQuarantineHref({
                      page: 1,
                      source: run.source_connection_id,
                      run: run.id,
                    })}
                    prefetch={false}
                    className={`text-amber-900 ${linkClass}`}
                  >
                    {run.records_quarantined.toLocaleString("en-US")}
                  </Link>
                ) : (
                  "0"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
