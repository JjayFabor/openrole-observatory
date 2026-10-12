import Link from "next/link";
import type { RunsSection } from "@/lib/api/types";
import { PipelineStatusBadge } from "@/components/dashboard/pipeline-status-badge";
import { Timestamp } from "@/components/dashboard/timestamp";
import { formatRunDuration } from "@/lib/dashboard/presentation";

export function SourceRecentRuns({
  section,
  sourceId,
  now,
}: {
  section: RunsSection;
  sourceId: string;
  now: number;
}) {
  return (
    <section aria-labelledby="source-recent-runs">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="source-recent-runs" className="text-base font-semibold">
          Recent Pipeline Runs
        </h2>
        <Link
          href={`/dashboard/runs?source=${sourceId}`}
          className="text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
        >
          View all runs
        </Link>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Up to 5 latest runs for this source.
      </p>
      {section.state === "unavailable" ? (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm">Unable to load recent pipeline runs.</p>
        </div>
      ) : section.runs.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm text-muted-foreground">No runs yet.</p>
        </div>
      ) : (
        <ol className="divide-y divide-border rounded-lg border border-border bg-card">
          {section.runs.map((run) => (
            <li key={run.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <Link
                  href={`/dashboard/runs/${run.id}?source=${sourceId}`}
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
              <div className="mt-3">
                <Timestamp value={run.started_at} now={now} />
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-4">
                <div>
                  <dt className="text-xs text-muted-foreground">Fetched</dt>
                  <dd className="mt-1 text-sm tabular-nums">
                    {run.records_fetched}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Changed</dt>
                  <dd className="mt-1 text-sm tabular-nums">
                    {run.jobs_changed}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Quarantined</dt>
                  <dd className="mt-1 text-sm tabular-nums">
                    {run.records_quarantined}
                  </dd>
                </div>
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
      )}
    </section>
  );
}
