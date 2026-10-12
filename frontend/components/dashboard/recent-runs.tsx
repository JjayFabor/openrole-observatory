import { Fragment } from "react";
import Link from "next/link";
import type { RunsSection } from "@/lib/api/types";
import { formatRunDuration } from "@/lib/dashboard/presentation";
import { PipelineStatusBadge } from "./pipeline-status-badge";
import { Timestamp } from "./timestamp";

export function RecentRuns({
  section,
  now,
}: {
  section: RunsSection;
  now: number;
}) {
  return (
    <section aria-labelledby="recent-runs">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="recent-runs" className="text-base font-semibold">
            Recent Pipeline Runs
          </h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Up to 5 latest runs across all sources.
          </p>
        </div>
        <Link
          href="/dashboard/runs"
          className="text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
        >
          View all runs
        </Link>
      </div>
      {section.state === "unavailable" ? (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm font-medium">
            Unable to load recent pipeline runs.
          </p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Pipeline activity is currently unavailable.
          </p>
        </div>
      ) : section.runs.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm font-medium">No pipeline runs yet.</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Source synchronization activity will appear here.
          </p>
        </div>
      ) : (
        <>
          <div
            role="region"
            aria-label="Recent pipeline runs table, scroll horizontally for metrics"
            tabIndex={0}
            className="hidden overflow-x-auto rounded-lg border border-border bg-card outline-none focus-visible:ring-2 focus-visible:ring-ring lg:block"
          >
            <table className="w-full text-left text-xs">
              <caption className="sr-only">
                Latest pipeline runs across all sources, with status,
                timestamps, duration, and ingestion counts.
              </caption>
              <thead className="border-b border-border bg-muted/40">
                <tr>
                  {[
                    "Status",
                    "Source",
                    "Started",
                    "Duration",
                    "Fetched",
                    "New",
                    "Changed",
                    "Unchanged",
                    "Quarantined",
                  ].map((label, index) => (
                    <th
                      key={label}
                      scope="col"
                      className={`whitespace-nowrap px-3 py-3 font-medium text-muted-foreground ${index >= 4 ? "text-right" : ""}`}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {section.runs.map((run) => (
                  <Fragment key={run.id}>
                    <tr className="border-t border-border align-top">
                      <td className="px-3 py-4">
                        <Link
                          href={`/dashboard/runs/${run.id}?source=${run.source_connection_id}`}
                          prefetch={false}
                          aria-label={`Pipeline run ${run.id}`}
                          className="rounded outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <PipelineStatusBadge status={run.status} />
                        </Link>
                      </td>
                      <td className="min-w-[160px] px-3 py-4">
                        <Link
                          href={`/dashboard/sources/${run.source_connection_id}`}
                          prefetch={false}
                          className="break-all font-mono text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {run.source_connection_id}
                        </Link>
                      </td>
                      <td className="min-w-[190px] px-3 py-4">
                        <Timestamp value={run.started_at} now={now} />
                      </td>
                      <td className="whitespace-nowrap px-3 py-4 tabular-nums">
                        {formatRunDuration(run)}
                      </td>
                      {[
                        run.records_fetched,
                        run.jobs_new,
                        run.jobs_changed,
                        run.jobs_unchanged,
                        run.records_quarantined,
                      ].map((value, index) => (
                        <td
                          key={index}
                          className="px-3 py-4 text-right tabular-nums"
                        >
                          {value}
                        </td>
                      ))}
                    </tr>
                    {(run.error_code || run.error_summary) && (
                      <tr>
                        <td colSpan={9} className="px-3 pb-4">
                          <p className="break-all font-mono font-medium">
                            {run.error_code}
                          </p>
                          <p className="mt-1 break-words leading-5 text-muted-foreground [overflow-wrap:anywhere]">
                            {run.error_summary}
                          </p>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <ol className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card lg:hidden">
            {section.runs.map((run) => (
              <li key={run.id} className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <Link
                    href={`/dashboard/runs/${run.id}?source=${run.source_connection_id}`}
                    prefetch={false}
                    aria-label={`Pipeline run ${run.id}`}
                    className="rounded outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <PipelineStatusBadge status={run.status} />
                  </Link>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    Duration: {formatRunDuration(run)}
                  </span>
                </div>
                <Link
                  href={`/dashboard/sources/${run.source_connection_id}`}
                  prefetch={false}
                  className="mt-3 inline-block break-all font-mono text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Source {run.source_connection_id}
                </Link>
                <div className="mt-3">
                  <Timestamp value={run.started_at} now={now} />
                </div>
                <dl className="mt-4 grid grid-cols-3 gap-x-4 gap-y-3">
                  {[
                    ["Fetched", run.records_fetched],
                    ["New", run.jobs_new],
                    ["Changed", run.jobs_changed],
                    ["Unchanged", run.jobs_unchanged],
                    ["Quarantined", run.records_quarantined],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-xs text-muted-foreground">{label}</dt>
                      <dd className="mt-1 text-sm font-medium tabular-nums">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>
                {(run.error_code || run.error_summary) && (
                  <div className="mt-4 border-t border-border pt-3 text-xs leading-5">
                    <p className="break-all font-mono font-medium">
                      {run.error_code}
                    </p>
                    <p className="mt-1 break-words text-muted-foreground [overflow-wrap:anywhere]">
                      {run.error_summary}
                    </p>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
