import Link from "next/link";
import type { QuarantineRecordDetail } from "@/lib/api/types";
import {
  formatErrorDetails,
  formatQuarantineTimestamp,
  getIdentityPresentation,
  getQuarantineCategoryLabel,
} from "@/lib/quarantine/presentation";
import { QuarantineStatusBadge } from "./quarantine-status-badge";
import { getSourceProviderLabel } from "@/lib/sources/presentation";

export function QuarantineDetail({
  record,
}: {
  record: QuarantineRecordDetail;
}) {
  const details = formatErrorDetails(record.error_details);
  const identity = getIdentityPresentation(record.external_job_id);
  const sectionClass = "rounded-lg border border-border bg-card p-5 sm:p-6";
  const detailsBlock = (
    <pre
      role="region"
      tabIndex={0}
      aria-label="Structured error details JSON"
      className="max-h-96 overflow-auto rounded-md border border-border bg-background p-4 font-mono text-xs leading-6 whitespace-pre-wrap outline-none [overflow-wrap:anywhere] focus-visible:ring-2 focus-visible:ring-ring"
    >
      {details}
    </pre>
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Quarantined Record
        </h1>
        <p className="mt-2 break-words text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
          {getSourceProviderLabel(record.source.provider)} ·{" "}
          {record.source.company_name}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <QuarantineStatusBadge status={record.status} />
          <span className="min-w-0 break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">
            {getQuarantineCategoryLabel(record.error_category)}
          </span>
        </div>
      </header>
      <section aria-labelledby="record-error" className={sectionClass}>
        <h2 id="record-error" className="text-base font-semibold">
          Processing Error
        </h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2">
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">Category</dt>
            <dd className="mt-1 break-all font-mono text-xs leading-6">
              {record.error_category}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">Code</dt>
            <dd className="mt-1 break-all font-mono text-xs leading-6">
              {record.error_code ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Created</dt>
            <dd className="mt-1 text-sm leading-6">
              <time dateTime={record.created_at}>
                {formatQuarantineTimestamp(record.created_at)}
              </time>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Resolved at</dt>
            <dd className="mt-1 text-sm leading-6">
              {record.resolved_at ? (
                <time dateTime={record.resolved_at}>
                  {formatQuarantineTimestamp(record.resolved_at)}
                </time>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div className="min-w-0 sm:col-span-2">
            <dt className="text-xs text-muted-foreground">Message</dt>
            <dd className="mt-2 break-words whitespace-pre-wrap text-sm leading-6 [overflow-wrap:anywhere]">
              {record.error_message}
            </dd>
          </div>
        </dl>
      </section>
      <section aria-labelledby="record-identity" className={sectionClass}>
        <h2 id="record-identity" className="text-base font-semibold">
          Record Identity
        </h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2">
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">External job ID</dt>
            <dd className="mt-1 break-all font-mono text-sm">
              {record.external_job_id ?? "—"}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">
              Raw record locator
            </dt>
            <dd className="mt-1 break-all font-mono text-sm">
              {record.raw_record_locator ?? "—"}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs leading-5 text-muted-foreground">
          {record.external_job_id === null
            ? "No external job ID could be recovered from this record."
            : "An external job ID was recovered from this record."}
        </p>
      </section>
      <section aria-labelledby="error-details" className={sectionClass}>
        <h2 id="error-details" className="mb-4 text-base font-semibold">
          Structured Error Details
        </h2>
        {details.length > 2000 ? (
          <details>
            <summary className="mb-4 cursor-pointer text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Show structured error details
            </summary>
            {detailsBlock}
          </details>
        ) : (
          detailsBlock
        )}
      </section>
      <section aria-labelledby="record-provenance" className={sectionClass}>
        <h2 id="record-provenance" className="text-base font-semibold">
          Provenance
        </h2>
        <dl className="mt-5 space-y-4">
          <div>
            <dt className="text-xs text-muted-foreground">
              QuarantineRecord ID
            </dt>
            <dd className="mt-1 break-all font-mono text-xs leading-6">
              {record.id}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">PipelineRun ID</dt>
            <dd className="mt-1">
              <Link
                href={`/dashboard/runs/${record.pipeline_run_id}?source=${record.source_connection_id}`}
                prefetch={false}
                className="break-all font-mono text-xs leading-6 text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
              >
                {record.pipeline_run_id}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              SourceConnection ID
            </dt>
            <dd className="mt-1">
              <Link
                href={`/dashboard/sources/${record.source_connection_id}`}
                prefetch={false}
                className="break-all font-mono text-xs leading-6 text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
              >
                {record.source_connection_id}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">RawSnapshot ID</dt>
            <dd className="mt-1 break-all font-mono text-xs leading-6">
              {record.raw_snapshot_id}
            </dd>
          </div>
        </dl>
      </section>
      <aside
        aria-labelledby="lifecycle-safety-note"
        className="border-l-2 border-border py-1 pl-4"
      >
        <h2 id="lifecycle-safety-note" className="text-sm font-medium">
          Lifecycle Safety Note
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {identity.note}
        </p>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          A quarantined record does not establish that the entire pipeline run
          failed.
        </p>
      </aside>
    </div>
  );
}
