import { SourceStatusBadge } from "@/components/sources/source-status-badge";
import Link from "next/link";
import { buildQuarantineHref } from "@/lib/quarantine/query-state";
import { getSourceProviderLabel } from "@/lib/sources/presentation";
import type { SourceSection } from "@/lib/api/types";
import { PipelineStatusBadge } from "./pipeline-status-badge";
import { Timestamp } from "./timestamp";

export function SourceHealthCard({
  section,
  now,
}: {
  section: SourceSection;
  now: number;
}) {
  return (
    <section aria-labelledby="source-health">
      <h2 id="source-health" className="mb-3 text-base font-semibold">
        Source Health
      </h2>
      {section.state === "unconfigured" ? (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm font-medium">
            No source configured for dashboard monitoring.
          </p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Recent pipeline runs are still shown below across all sources.
          </p>
        </div>
      ) : section.state === "unavailable" ? (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm font-medium">Unable to load source health.</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {section.reason === "not_found"
              ? "The configured source could not be found."
              : "Source information is currently unavailable."}
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
            <div>
              <h3 className="text-sm font-semibold">
                {getSourceProviderLabel(section.source.provider)}
              </h3>
              <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                {section.source.id}
              </p>
              <Link
                href={`/dashboard/sources/${section.source.id}`}
                prefetch={false}
                className="mt-1 inline-block text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
              >
                View source
              </Link>
            </div>
            <SourceStatusBadge active={section.source.is_active} />
          </div>
          <dl className="grid gap-5 px-5 py-5 sm:grid-cols-2">
            <div>
              <dt className="mb-2 text-xs text-muted-foreground">
                Last attempted sync
              </dt>
              <dd>
                <Timestamp
                  value={section.source.last_attempted_sync_at}
                  now={now}
                />
              </dd>
            </div>
            <div>
              <dt className="mb-2 text-xs text-muted-foreground">
                Last successful sync
              </dt>
              <dd>
                <Timestamp
                  value={section.source.last_successful_sync_at}
                  now={now}
                />
              </dd>
            </div>
          </dl>
          <div className="border-t border-border px-5 py-5">
            {section.source.latest_run ? (
              <>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-medium">Latest run</h4>
                  <PipelineStatusBadge
                    status={section.source.latest_run.status}
                  />
                </div>
                <dl className="grid grid-cols-3 gap-x-4 gap-y-4 sm:grid-cols-6">
                  {[
                    ["Fetched", section.source.latest_run.records_fetched],
                    ["Valid", section.source.latest_run.records_valid],
                    ["New", section.source.latest_run.jobs_new],
                    ["Changed", section.source.latest_run.jobs_changed],
                    ["Unchanged", section.source.latest_run.jobs_unchanged],
                    [
                      "Quarantined",
                      section.source.latest_run.records_quarantined,
                    ],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-xs text-muted-foreground">{label}</dt>
                      <dd className="mt-1 text-sm font-medium tabular-nums">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>
                {section.source.latest_run.records_quarantined > 0 && (
                  <Link
                    prefetch={false}
                    href={buildQuarantineHref({
                      page: 1,
                      run: section.source.latest_run.id,
                    })}
                    className="mt-4 inline-block text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    View quarantined records
                  </Link>
                )}
                {(section.source.latest_run.error_code ||
                  section.source.latest_run.error_summary) && (
                  <div className="mt-4 border-t border-border pt-4 text-xs leading-5">
                    <p className="break-all font-mono font-medium">
                      {section.source.latest_run.error_code}
                    </p>
                    <p className="mt-1 break-words text-muted-foreground [overflow-wrap:anywhere]">
                      {section.source.latest_run.error_summary}
                    </p>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                No pipeline run recorded for this source yet.
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
