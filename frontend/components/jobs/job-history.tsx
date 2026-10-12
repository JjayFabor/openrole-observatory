import Link from "next/link";
import type { JobDetailResult, JsonValue } from "@/lib/api/types";
import { formatAbsoluteTimestamp } from "@/lib/dashboard/presentation";
import { formatSourceTimestamp } from "@/lib/sources/presentation";
import {
  groupJobChanges,
  formatEmploymentType,
  formatSalary,
  formatWorkplaceType,
  getChangeFieldLabel,
  getChangeTypeLabel,
  getLifecycleEventLabel,
  getLifecycleLabel,
} from "@/lib/jobs/presentation";
import type { JobHistoryQuery } from "@/lib/jobs/history-query";
import { Badge } from "@/components/ui/badge";
import { JobDescription } from "./job-description";
import { JobHistoryPagination } from "./job-history-pagination";

type AvailableDetail = Extract<JobDetailResult, { state: "available" }>;
const linkClass =
  "text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring";

function RecordedValue({
  value,
  field,
  label,
}: {
  value: JsonValue;
  field: string;
  label: string;
}) {
  if (value === null) return <span className="block">—</span>;
  if (typeof value === "object")
    return (
      <details className="min-w-0 max-w-full">
        <summary className="cursor-pointer rounded outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Inspect recorded value
        </summary>
        <pre
          role="region"
          aria-label={label}
          tabIndex={0}
          className="mt-2 max-h-64 max-w-full overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted/30 p-3 text-xs leading-5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {JSON.stringify(value, null, 2)}
        </pre>
      </details>
    );
  if (typeof value === "string" && field === "workplace_type") {
    const label = formatWorkplaceType(value);
    return (
      <span className="block min-w-0 max-w-full break-words [overflow-wrap:anywhere]">
        {label === "—" ? value : label}
      </span>
    );
  }
  if (typeof value === "string" && field === "employment_type") {
    const label = formatEmploymentType(value);
    return (
      <span className="block min-w-0 max-w-full break-words [overflow-wrap:anywhere]">
        {label === "—" ? value : label}
      </span>
    );
  }
  return (
    <span className="block min-w-0 max-w-full break-words [overflow-wrap:anywhere]">
      {String(value)}
    </span>
  );
}

export function JobVersionHistory({
  detail,
  query,
}: {
  detail: AvailableDetail;
  query: JobHistoryQuery;
}) {
  const section = detail.versions;
  return (
    <section
      id="versions"
      aria-labelledby="versions-heading"
      className="scroll-mt-6"
    >
      <h2 id="versions-heading" className="text-base font-semibold">
        Version History
      </h2>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        Canonical content in ascending version order. Observation times describe
        evidence collected by OpenRole.
      </p>
      {section.state === "unavailable" ? (
        <p className="mt-4 rounded-lg border border-border bg-card p-5 text-sm">
          Unable to load version history.
        </p>
      ) : (
        <>
          {section.data.items.length === 0 ? (
            <p className="mt-4 rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">
              {query.versions > 1
                ? "No versions on this page."
                : "No versions available."}
            </p>
          ) : (
            <ol className="mt-4 space-y-3">
              {section.data.items.map((version) => (
                <li
                  key={version.id}
                  className="rounded-lg border border-border bg-card p-5 sm:p-6"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-semibold">
                      v{version.version_number} ·{" "}
                      <span className="break-words [overflow-wrap:anywhere]">
                        {version.title}
                      </span>
                    </h3>
                    {version.is_current && (
                      <Badge className="border-primary/20 bg-accent text-accent-foreground">
                        Current
                      </Badge>
                    )}
                  </div>
                  <dl className="mt-4 grid gap-4 text-xs sm:grid-cols-2">
                    {[
                      [
                        "Observed from",
                        formatAbsoluteTimestamp(version.effective_from),
                      ],
                      [
                        "Observed until",
                        formatSourceTimestamp(version.effective_to),
                      ],
                      ["Location", version.location_text ?? "—"],
                      [
                        "Workplace",
                        formatWorkplaceType(version.workplace_type),
                      ],
                      [
                        "Employment type",
                        formatEmploymentType(version.employment_type),
                      ],
                      ["Salary", formatSalary(version)],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <dt className="text-muted-foreground">{label}</dt>
                        <dd className="mt-1 break-words leading-5 [overflow-wrap:anywhere]">
                          {value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <details className="mt-4">
                    <summary className="cursor-pointer rounded text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      Description and version provenance
                    </summary>
                    <div className="mt-4">
                      <JobDescription description={version.description} />
                    </div>
                    <dl className="mt-4 space-y-3 text-xs">
                      {[
                        ["Version ID", version.id],
                        ["SourceObservation ID", version.source_observation_id],
                        ["Canonical content hash", version.content_hash],
                      ].map(([label, value]) => (
                        <div key={label}>
                          <dt className="text-muted-foreground">{label}</dt>
                          <dd className="mt-1 break-all font-mono leading-5">
                            {value}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                </li>
              ))}
            </ol>
          )}
          <JobHistoryPagination
            jobId={detail.job.id}
            state={query}
            section="versions"
            hasNext={section.data.hasNext}
          />
        </>
      )}
    </section>
  );
}

export function JobChangeHistory({
  detail,
  query,
}: {
  detail: AvailableDetail;
  query: JobHistoryQuery;
}) {
  const section = detail.changes;
  return (
    <section
      id="changes"
      aria-labelledby="changes-heading"
      className="min-w-0 max-w-full scroll-mt-6"
    >
      <h2 id="changes-heading" className="text-base font-semibold">
        Field-Level Changes
      </h2>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        Persisted changes between canonical versions. Transitions may continue
        on the next page.
      </p>
      {section.state === "unavailable" ? (
        <p className="mt-4 rounded-lg border border-border bg-card p-5 text-sm">
          Unable to load change history.
        </p>
      ) : (
        <>
          {section.data.items.length === 0 ? (
            <p className="mt-4 rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">
              {query.changes > 1
                ? "No changes on this page."
                : "No material changes recorded."}
            </p>
          ) : (
            <div className="mt-4 min-w-0 max-w-full space-y-3">
              {groupJobChanges(section.data.items).map((group) => (
                <section
                  key={`${group.from}/${group.to}`}
                  aria-label={`Changes from v${group.from} to v${group.to}`}
                  className="min-w-0 max-w-full rounded-lg border border-border bg-card p-5 sm:p-6"
                >
                  <h3 className="text-sm font-semibold">
                    v{group.from} → v{group.to}
                  </h3>
                  <ol className="mt-4 divide-y divide-border">
                    {group.items.map((change) => (
                      <li
                        key={change.id}
                        className="min-w-0 py-4 first:pt-0 last:pb-0"
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <h4 className="break-words text-sm font-medium [overflow-wrap:anywhere]">
                            {getChangeFieldLabel(change.field_name)} ·{" "}
                            {getChangeTypeLabel(change.change_type)}
                          </h4>
                          <time
                            dateTime={change.detected_at}
                            className="text-xs text-muted-foreground"
                          >
                            {formatAbsoluteTimestamp(change.detected_at)}
                          </time>
                        </div>
                        {change.field_name === "description" ? (
                          <p className="mt-2 text-xs leading-5 text-muted-foreground">
                            Description{" "}
                            {getChangeTypeLabel(
                              change.change_type,
                            ).toLowerCase()}
                            . Inspect the corresponding content in{" "}
                            <a href="#versions" className={linkClass}>
                              Version History
                            </a>
                            .
                          </p>
                        ) : (
                          <dl className="mt-3 grid min-w-0 max-w-full grid-cols-1 gap-3 text-xs sm:grid-cols-2">
                            <div className="min-w-0">
                              <dt className="mb-1 text-muted-foreground">
                                Before
                              </dt>
                              <dd className="min-w-0 max-w-full">
                                <RecordedValue
                                  value={change.old_value}
                                  field={change.field_name}
                                  label={`Before ${getChangeFieldLabel(change.field_name)}`}
                                />
                              </dd>
                            </div>
                            <div className="min-w-0">
                              <dt className="mb-1 text-muted-foreground">
                                After
                              </dt>
                              <dd className="min-w-0 max-w-full">
                                <RecordedValue
                                  value={change.new_value}
                                  field={change.field_name}
                                  label={`After ${getChangeFieldLabel(change.field_name)}`}
                                />
                              </dd>
                            </div>
                          </dl>
                        )}
                      </li>
                    ))}
                  </ol>
                </section>
              ))}
            </div>
          )}
          <JobHistoryPagination
            jobId={detail.job.id}
            state={query}
            section="changes"
            hasNext={section.data.hasNext}
          />
        </>
      )}
    </section>
  );
}

export function JobLifecycleHistory({
  detail,
  query,
}: {
  detail: AvailableDetail;
  query: JobHistoryQuery;
}) {
  const section = detail.lifecycle;
  return (
    <section
      id="lifecycle"
      aria-labelledby="lifecycle-history-heading"
      className="scroll-mt-6"
    >
      <h2 id="lifecycle-history-heading" className="text-base font-semibold">
        Lifecycle Timeline
      </h2>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        Source observation evidence; these events do not describe exact employer
        actions.
      </p>
      {section.state === "unavailable" ? (
        <p className="mt-4 rounded-lg border border-border bg-card p-5 text-sm">
          Unable to load lifecycle history.
        </p>
      ) : (
        <>
          {section.data.summary.events.length === 0 ? (
            <p className="mt-4 rounded-lg border border-border bg-card p-5 text-sm text-muted-foreground">
              {query.lifecycle > 1
                ? "No lifecycle events on this page."
                : "No lifecycle transitions recorded."}
            </p>
          ) : (
            <ol className="mt-4 divide-y divide-border rounded-lg border border-border bg-card">
              {section.data.summary.events.map((event) => (
                <li key={event.id} className="p-5 sm:p-6">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-medium">
                      {getLifecycleEventLabel(event.event_type)}
                    </h3>
                    <time
                      dateTime={event.occurred_at}
                      className="text-xs text-muted-foreground"
                    >
                      {formatAbsoluteTimestamp(event.occurred_at)}
                    </time>
                  </div>
                  <p className="mt-2 text-xs leading-5">
                    {event.previous_status === null
                      ? "—"
                      : getLifecycleLabel(event.previous_status)}{" "}
                    →{" "}
                    {event.new_status === null
                      ? "—"
                      : getLifecycleLabel(event.new_status)}
                  </p>
                  <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs">
                    {["consecutive_absent_runs", "confirmation_threshold"].map(
                      (key) =>
                        typeof event.metadata[key] === "number" ? (
                          <div key={key}>
                            <dt className="text-muted-foreground">
                              {key === "consecutive_absent_runs"
                                ? "Consecutive absent runs"
                                : "Confirmation threshold"}
                            </dt>
                            <dd className="mt-1 tabular-nums">
                              {String(event.metadata[key])}
                            </dd>
                          </div>
                        ) : null,
                    )}
                  </dl>
                  <Link
                    href={`/dashboard/runs/${event.pipeline_run_id}?source=${detail.job.source_connection_id}`}
                    prefetch={false}
                    className={`mt-3 inline-block break-all font-mono text-xs ${linkClass}`}
                  >
                    Run {event.pipeline_run_id}
                  </Link>
                </li>
              ))}
            </ol>
          )}
          <JobHistoryPagination
            jobId={detail.job.id}
            state={query}
            section="lifecycle"
            hasNext={section.data.hasNext}
          />
        </>
      )}
    </section>
  );
}
