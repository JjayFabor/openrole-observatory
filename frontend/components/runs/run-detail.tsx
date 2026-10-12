import Link from "next/link";
import type { RunDetailResult } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { PipelineStatusBadge } from "@/components/dashboard/pipeline-status-badge";
import { SourceStatusBadge } from "@/components/sources/source-status-badge";
import {
  formatAbsoluteTimestamp,
  formatRunDuration,
} from "@/lib/dashboard/presentation";
import {
  formatSourceTimestamp,
  getSourceProviderLabel,
} from "@/lib/sources/presentation";
import { buildJobsHref } from "@/lib/jobs/query-state";
import { buildQuarantineHref } from "@/lib/quarantine/query-state";

type AvailableRun = Extract<RunDetailResult, { state: "available" }>;
const panel = "rounded-lg border border-border bg-card p-5 sm:p-6";
const linkClass =
  "text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring";
export function RunDetail({ detail }: { detail: AvailableRun }) {
  const { run, source } = detail;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Pipeline Run</h1>
        <p className="mt-2 break-all font-mono text-xs leading-5 text-muted-foreground">
          {run.id}
        </p>
        <div className="mt-3">
          <PipelineStatusBadge status={run.status} />
        </div>
        {source.state === "available" && (
          <p className="mt-3 break-words text-sm text-muted-foreground [overflow-wrap:anywhere]">
            {getSourceProviderLabel(source.data.provider)} ·{" "}
            {source.data.company.name}
          </p>
        )}
      </header>
      <section aria-labelledby="run-summary-heading" className={panel}>
        <h2 id="run-summary-heading" className="text-base font-semibold">
          Run Summary
        </h2>
        <dl className="mt-5 grid gap-5 text-sm sm:grid-cols-2 lg:grid-cols-3">
          {[
            ["Started", formatAbsoluteTimestamp(run.started_at)],
            ["Completed", formatSourceTimestamp(run.completed_at)],
            ["Duration", formatRunDuration(run)],
            ["Created", formatAbsoluteTimestamp(run.created_at)],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="mt-1 leading-6">{value}</dd>
            </div>
          ))}
        </dl>
      </section>
      {run.status === "completed_with_errors" && (
        <section
          aria-label="Partial synchronization outcome"
          className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-amber-950"
        >
          <h2 className="text-sm font-semibold">
            Synchronization completed with record errors.
          </h2>
          <p className="mt-2 text-sm leading-6">
            The source synchronization completed, but some records could not be
            processed. {run.records_quarantined.toLocaleString("en-US")} records
            were quarantined.
          </p>
        </section>
      )}
      {(run.error_code || run.error_summary) && (
        <section aria-labelledby="run-error-heading" className={panel}>
          <h2 id="run-error-heading" className="text-base font-semibold">
            {run.status === "failed"
              ? "Failure Information"
              : "Recorded Diagnostic"}
          </h2>
          <dl className="mt-4 space-y-4 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">Error code</dt>
              <dd className="mt-1 break-all font-mono text-xs">
                {run.error_code ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Error summary</dt>
              <dd className="mt-1 break-words leading-6 [overflow-wrap:anywhere]">
                {run.error_summary ?? "—"}
              </dd>
            </div>
          </dl>
        </section>
      )}
      <section aria-labelledby="run-metrics-heading" className={panel}>
        <h2 id="run-metrics-heading" className="text-base font-semibold">
          Pipeline Metrics
        </h2>
        <dl className="mt-5 grid grid-cols-2 gap-5 sm:grid-cols-3">
          {[
            ["Records fetched", run.records_fetched],
            ["Records valid", run.records_valid],
            ["Records quarantined", run.records_quarantined],
            ["Jobs new", run.jobs_new],
            ["Jobs changed", run.jobs_changed],
            ["Jobs unchanged", run.jobs_unchanged],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="mt-1 text-base tabular-nums">
                {typeof value === "number"
                  ? value.toLocaleString("en-US")
                  : value}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-5 text-xs leading-5 text-muted-foreground">
          Fetched source records and logical jobs describe different stages of
          the pipeline.
        </p>
      </section>
      <section aria-labelledby="run-source-heading" className={panel}>
        <h2 id="run-source-heading" className="text-base font-semibold">
          Source
        </h2>
        {source.state === "available" ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <p className="break-words text-sm [overflow-wrap:anywhere]">
              {source.data.company.name} ·{" "}
              {getSourceProviderLabel(source.data.provider)}
            </p>
            <SourceStatusBadge active={source.data.is_active} />
          </div>
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">
            Unable to load source summary. Run facts remain available.
          </p>
        )}
        <Link
          href={`/dashboard/sources/${run.source_connection_id}`}
          prefetch={false}
          className={`mt-4 inline-block text-sm ${linkClass}`}
        >
          View source
        </Link>
        <p className="mt-3 break-all font-mono text-xs leading-5 text-muted-foreground">
          {run.source_connection_id}
        </p>
      </section>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" asChild>
          <Link
            href={buildQuarantineHref({
              page: 1,
              source: run.source_connection_id,
              run: run.id,
            })}
          >
            View run quarantine
          </Link>
        </Button>
        <Button variant="outline" asChild>
          <Link
            href={buildJobsHref({ page: 1, source: run.source_connection_id })}
          >
            View source jobs
          </Link>
        </Button>
      </div>
      <section aria-labelledby="run-provenance-heading" className={panel}>
        <h2 id="run-provenance-heading" className="text-base font-semibold">
          Provenance
        </h2>
        <dl className="mt-5 space-y-4 text-xs">
          <div>
            <dt className="text-muted-foreground">PipelineRun ID</dt>
            <dd className="mt-1 break-all font-mono leading-5">{run.id}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">SourceConnection ID</dt>
            <dd className="mt-1 break-all font-mono leading-5">
              {run.source_connection_id}
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
