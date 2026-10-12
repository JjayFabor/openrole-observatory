import Link from "next/link";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { PipelineStatusBadge } from "@/components/dashboard/pipeline-status-badge";
import { Timestamp } from "@/components/dashboard/timestamp";
import type {
  RunsSection,
  SourceQuarantineSection,
  SourceRead,
} from "@/lib/api/types";
import { formatRunDuration } from "@/lib/dashboard/presentation";
import { buildJobsHref } from "@/lib/jobs/query-state";
import { buildQuarantineHref } from "@/lib/quarantine/query-state";
import {
  formatSourceTimestamp,
  getSafeCareersUrl,
  getSourceProviderLabel,
  isNeverSynchronized,
} from "@/lib/sources/presentation";
import { SourceStatusBadge } from "./source-status-badge";
import { SourceRecentRuns } from "./source-recent-runs";
import { SourceRecentQuarantine } from "./source-recent-quarantine";

export function SourceDetail({
  source,
  runs,
  quarantine,
  now,
  action,
}: {
  source: SourceRead;
  runs: RunsSection;
  quarantine: SourceQuarantineSection;
  now: number;
  action?: ReactNode;
}) {
  const careersUrl = getSafeCareersUrl(source.company.careers_url);
  const run = source.latest_run;
  const sectionClass = "rounded-lg border border-border bg-card p-5 sm:p-6";
  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h1 className="break-words text-2xl font-semibold tracking-tight [overflow-wrap:anywhere]">
            {source.company.name}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <p className="text-sm text-muted-foreground">
              {getSourceProviderLabel(source.provider)}
            </p>
            <SourceStatusBadge active={source.is_active} />
          </div>
        </div>
        {action}
      </header>
      <section aria-labelledby="source-summary" className={sectionClass}>
        <h2 id="source-summary" className="text-base font-semibold">
          Source Summary
        </h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2">
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">Company</dt>
            <dd className="mt-1 break-words text-sm [overflow-wrap:anywhere]">
              {source.company.name}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">Domain</dt>
            <dd className="mt-1 break-all text-sm">
              {source.company.domain ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Provider</dt>
            <dd className="mt-1 text-sm">
              {getSourceProviderLabel(source.provider)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Active state</dt>
            <dd className="mt-1">
              <SourceStatusBadge active={source.is_active} />
            </dd>
          </div>
          <div className="min-w-0 sm:col-span-2">
            <dt className="text-xs text-muted-foreground">Careers page</dt>
            <dd className="mt-1 text-sm">
              {careersUrl ? (
                <a
                  href={careersUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="break-all text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="Company careers page, opens in a new tab"
                >
                  {careersUrl}
                </a>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>
        <div className="mt-5 flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link href={buildJobsHref({ page: 1, source: source.id })}>
              View jobs
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href={`/dashboard/runs?source=${source.id}`}>
              View all runs
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href={buildQuarantineHref({ page: 1, source: source.id })}>
              View all quarantine
            </Link>
          </Button>
        </div>
      </section>
      <section aria-labelledby="source-freshness" className={sectionClass}>
        <h2 id="source-freshness" className="text-base font-semibold">
          Freshness
        </h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2">
          <div>
            <dt className="mb-2 text-xs text-muted-foreground">
              Last attempted sync
            </dt>
            <dd>
              {source.last_attempted_sync_at ? (
                <Timestamp value={source.last_attempted_sync_at} now={now} />
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt className="mb-2 text-xs text-muted-foreground">
              Last successful sync
            </dt>
            <dd>
              {source.last_successful_sync_at ? (
                <Timestamp value={source.last_successful_sync_at} now={now} />
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>
        {isNeverSynchronized(source) && (
          <p className="mt-4 text-sm text-muted-foreground">
            Never synchronized.
          </p>
        )}
        {run?.status === "failed" && (
          <div className="mt-5 border-l-2 border-border pl-4">
            <p className="text-sm font-medium">
              Latest synchronization failed.
            </p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Last successful synchronization:{" "}
              {formatSourceTimestamp(source.last_successful_sync_at)}
            </p>
          </div>
        )}
      </section>
      <section aria-labelledby="source-latest-run" className={sectionClass}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="source-latest-run" className="text-base font-semibold">
            Latest Pipeline Run
          </h2>
          {run && <PipelineStatusBadge status={run.status} />}
        </div>
        {run ? (
          <>
            <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
              <Timestamp value={run.started_at} now={now} />
              <span className="text-xs tabular-nums text-muted-foreground">
                Duration: {formatRunDuration(run)}
              </span>
            </div>
            <dl className="mt-5 grid grid-cols-3 gap-4 sm:grid-cols-5">
              {[
                ["Fetched", run.records_fetched],
                ["New", run.jobs_new],
                ["Changed", run.jobs_changed],
                ["Unchanged", run.jobs_unchanged],
                ["Quarantined", run.records_quarantined],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="mt-1 text-sm tabular-nums">{value}</dd>
                </div>
              ))}
            </dl>
            {(run.error_code || run.error_summary) && (
              <div className="mt-5 border-t border-border pt-4 text-xs leading-5">
                <p className="break-all font-mono font-medium">
                  {run.error_code}
                </p>
                <p className="mt-1 break-words text-muted-foreground [overflow-wrap:anywhere]">
                  {run.error_summary}
                </p>
              </div>
            )}
            <Link
              href={`/dashboard/runs/${run.id}?source=${source.id}`}
              prefetch={false}
              className="mt-4 inline-block text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
            >
              View run
            </Link>
          </>
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">No runs yet.</p>
        )}
      </section>
      <SourceRecentRuns section={runs} sourceId={source.id} now={now} />
      <SourceRecentQuarantine section={quarantine} sourceId={source.id} />
      <section aria-labelledby="source-provenance" className={sectionClass}>
        <h2 id="source-provenance" className="text-base font-semibold">
          Provenance
        </h2>
        <dl className="mt-5 space-y-4">
          <div>
            <dt className="text-xs text-muted-foreground">
              SourceConnection ID
            </dt>
            <dd className="mt-1 break-all font-mono text-xs leading-6">
              {source.id}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Company ID</dt>
            <dd className="mt-1 break-all font-mono text-xs leading-6">
              {source.company_id}
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
