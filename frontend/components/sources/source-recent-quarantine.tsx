import Link from "next/link";
import type { SourceQuarantineSection } from "@/lib/api/types";
import { QuarantineStatusBadge } from "@/components/quarantine/quarantine-status-badge";
import {
  formatQuarantineTimestamp,
  getQuarantineCategoryLabel,
} from "@/lib/quarantine/presentation";
import { buildQuarantineHref } from "@/lib/quarantine/query-state";

export function SourceRecentQuarantine({
  section,
  sourceId,
}: {
  section: SourceQuarantineSection;
  sourceId: string;
}) {
  return (
    <section aria-labelledby="source-recent-quarantine">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="source-recent-quarantine" className="text-base font-semibold">
          Recent Quarantine Activity
        </h2>
        <Link
          href={buildQuarantineHref({ page: 1, source: sourceId })}
          className="text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
        >
          View all quarantine
        </Link>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Up to 5 latest record-level errors for this source.
      </p>
      {section.state === "unavailable" ? (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm">Unable to load recent quarantine activity.</p>
        </div>
      ) : section.records.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-sm text-muted-foreground">
            No recent quarantined records.
          </p>
        </div>
      ) : (
        <ol className="divide-y divide-border rounded-lg border border-border bg-card">
          {section.records.map((record) => (
            <li key={record.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <Link
                  href={`/dashboard/quarantine/${record.id}`}
                  prefetch={false}
                  className="min-w-0 break-words text-sm font-medium underline-offset-4 outline-none [overflow-wrap:anywhere] hover:text-primary hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {getQuarantineCategoryLabel(record.error_category)}
                </Link>
                <QuarantineStatusBadge status={record.status} />
              </div>
              <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                {record.external_job_id ?? "Identity unavailable"}
              </p>
              <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2">
                <time
                  dateTime={record.created_at}
                  className="text-xs text-muted-foreground"
                >
                  {formatQuarantineTimestamp(record.created_at)}
                </time>
                <Link
                  href={`/dashboard/runs/${record.pipeline_run_id}?source=${sourceId}`}
                  prefetch={false}
                  className="text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Related run
                </Link>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
