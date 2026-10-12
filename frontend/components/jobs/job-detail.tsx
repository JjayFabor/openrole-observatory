import Link from "next/link";
import type { JobDetailResult } from "@/lib/api/types";
import type { JobHistoryQuery } from "@/lib/jobs/history-query";
import {
  formatEmploymentType,
  formatSalary,
  formatWorkplaceType,
} from "@/lib/jobs/presentation";
import { formatAbsoluteTimestamp } from "@/lib/dashboard/presentation";
import {
  formatSourceTimestamp,
  getSafeCareersUrl,
  getSourceProviderLabel,
} from "@/lib/sources/presentation";
import { LifecycleBadge } from "./lifecycle-badge";
import { JobDescription } from "./job-description";
import {
  JobChangeHistory,
  JobLifecycleHistory,
  JobVersionHistory,
} from "./job-history";

type AvailableDetail = Extract<JobDetailResult, { state: "available" }>;
const panel = "rounded-lg border border-border bg-card p-5 sm:p-6";
const linkClass =
  "text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring";
export function JobDetail({
  detail,
  query,
}: {
  detail: AvailableDetail;
  query: JobHistoryQuery;
}) {
  const { job, source, lifecycle } = detail;
  const version = job.current_version;
  const sourceUrl = getSafeCareersUrl(version.source_url);
  return (
    <div className="space-y-6">
      <header>
        <h1 className="break-words text-2xl font-semibold tracking-tight [overflow-wrap:anywhere]">
          {version.title}
        </h1>
        {source.state === "available" ? (
          <p className="mt-2 break-words text-sm text-muted-foreground [overflow-wrap:anywhere]">
            {source.data.company.name} ·{" "}
            {getSourceProviderLabel(source.data.provider)}
          </p>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            Company and provider information is currently unavailable.
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <LifecycleBadge status={job.lifecycle_status} />
          <p className="min-w-0 break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">
            {version.location_text ?? "—"} ·{" "}
            {formatEmploymentType(version.employment_type)}
          </p>
        </div>
        <p className="mt-3 text-xs leading-5 text-muted-foreground">
          Last observed {formatAbsoluteTimestamp(job.last_seen_at)} · Current
          version v{version.version_number}
        </p>
      </header>
      <nav
        aria-label="Job investigation sections"
        className="flex flex-wrap gap-x-5 gap-y-2 text-xs"
      >
        {[
          ["current-listing", "Current listing"],
          ["versions", "Versions"],
          ["changes", "Changes"],
          ["lifecycle", "Lifecycle"],
          ["provenance", "Provenance"],
        ].map(([id, label]) => (
          <a key={id} href={`#${id}`} className={linkClass}>
            {label}
          </a>
        ))}
      </nav>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section
          id="current-listing"
          aria-labelledby="current-listing-heading"
          className={`${panel} min-w-0 scroll-mt-6`}
        >
          <h2 id="current-listing-heading" className="text-base font-semibold">
            Current Listing
          </h2>
          <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
            {[
              ["Title", version.title],
              ["Location", version.location_text ?? "—"],
              ["City", version.city ?? "—"],
              ["Region", version.region ?? "—"],
              ["Country code", version.country_code ?? "—"],
              ["Workplace", formatWorkplaceType(version.workplace_type)],
              [
                "Employment type",
                formatEmploymentType(version.employment_type),
              ],
              ["Salary", formatSalary(version)],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 break-words [overflow-wrap:anywhere]">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-5">
            {sourceUrl ? (
              <a
                href={sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={`text-sm ${linkClass}`}
              >
                View source listing
                <span className="sr-only">, opens in a new tab</span>
              </a>
            ) : (
              <p className="text-xs text-muted-foreground">Source listing: —</p>
            )}
          </div>
          <h3 className="mb-3 mt-6 border-t border-border pt-5 text-sm font-semibold">
            Description
          </h3>
          <JobDescription description={version.description} />
          <details className="mt-5 border-t border-border pt-4">
            <summary className="cursor-pointer rounded text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Canonical metadata
            </summary>
            <pre
              role="region"
              aria-label="Current canonical metadata"
              tabIndex={0}
              className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted/30 p-3 text-xs leading-5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {JSON.stringify(version.canonical_metadata, null, 2)}
            </pre>
          </details>
        </section>
        <div className="min-w-0 space-y-6">
          <section
            aria-labelledby="lifecycle-summary-heading"
            className={panel}
          >
            <h2
              id="lifecycle-summary-heading"
              className="text-base font-semibold"
            >
              Lifecycle Summary
            </h2>
            {lifecycle.state === "unavailable" ? (
              <p className="mt-4 text-sm text-muted-foreground">
                Unable to load lifecycle summary.
              </p>
            ) : (
              <>
                <div className="mt-4">
                  <LifecycleBadge
                    status={lifecycle.data.summary.current_status}
                  />
                </div>
                <dl className="mt-4 space-y-4 text-xs">
                  {[
                    [
                      "First observed",
                      formatAbsoluteTimestamp(
                        lifecycle.data.summary.first_seen_at,
                      ),
                    ],
                    [
                      "Last observed",
                      formatAbsoluteTimestamp(
                        lifecycle.data.summary.last_seen_at,
                      ),
                    ],
                    [
                      "First absence detected",
                      formatSourceTimestamp(
                        lifecycle.data.summary.absence_first_detected_at,
                      ),
                    ],
                    [
                      "Absence confirmed",
                      formatSourceTimestamp(
                        lifecycle.data.summary.no_longer_observed_at,
                      ),
                    ],
                    [
                      "Reappeared",
                      formatSourceTimestamp(
                        lifecycle.data.summary.reappeared_at,
                      ),
                    ],
                    [
                      "Consecutive absent runs",
                      String(lifecycle.data.summary.consecutive_absent_runs),
                    ],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-muted-foreground">{label}</dt>
                      <dd className="mt-1 leading-5">{value}</dd>
                    </div>
                  ))}
                </dl>
                {lifecycle.data.summary.current_status === "observed" &&
                  lifecycle.data.summary.consecutive_absent_runs === 1 && (
                    <p className="mt-4 border-l-2 border-border pl-3 text-xs leading-5 text-muted-foreground">
                      Absence detected; awaiting confirmation. Status remains
                      Observed.
                    </p>
                  )}
              </>
            )}
          </section>
          <section aria-labelledby="job-source-heading" className={panel}>
            <h2 id="job-source-heading" className="text-base font-semibold">
              Source
            </h2>
            <Link
              href={`/dashboard/sources/${job.source_connection_id}`}
              prefetch={false}
              className={`mt-4 inline-block text-sm ${linkClass}`}
            >
              View source
            </Link>
            <p className="mt-3 break-all font-mono text-xs leading-5 text-muted-foreground">
              {job.source_connection_id}
            </p>
            {source.state === "unavailable" && (
              <p className="mt-3 text-xs leading-5 text-muted-foreground">
                Unable to load source summary.
              </p>
            )}
          </section>
        </div>
      </div>
      <JobVersionHistory detail={detail} query={query} />
      <JobChangeHistory detail={detail} query={query} />
      <JobLifecycleHistory detail={detail} query={query} />
      <section
        id="provenance"
        aria-labelledby="job-provenance-heading"
        className={`${panel} scroll-mt-6`}
      >
        <h2 id="job-provenance-heading" className="text-base font-semibold">
          Provenance
        </h2>
        <dl className="mt-5 grid gap-4 text-xs sm:grid-cols-2">
          {[
            ["Job ID", job.id],
            ["External job ID", job.external_job_id],
            ["Company ID", job.company_id],
            ["SourceConnection ID", job.source_connection_id],
            ["Current JobVersion ID", version.id],
            ["Current SourceObservation ID", version.source_observation_id],
            ["Canonical content hash", version.content_hash],
            ["Observed from", formatAbsoluteTimestamp(version.effective_from)],
            ["Observed until", formatSourceTimestamp(version.effective_to)],
          ].map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="mt-1 break-all font-mono leading-5">{value}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
