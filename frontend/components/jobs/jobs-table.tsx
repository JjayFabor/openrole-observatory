import Link from "next/link";
import type { JobListItem } from "@/lib/api/types";
import { formatAbsoluteTimestamp } from "@/lib/dashboard/presentation";
import {
  formatEmploymentType,
  formatWorkplaceType,
} from "@/lib/jobs/presentation";
import { LifecycleBadge } from "./lifecycle-badge";
import { getSourceProviderLabel } from "@/lib/sources/presentation";

export function JobsTable({ jobs }: { jobs: JobListItem[] }) {
  return (
    <div>
      <p className="mb-2 text-xs text-muted-foreground lg:hidden">
        Scroll the table to see all listing details.
      </p>
      <div
        role="region"
        aria-label="Jobs listing table, horizontally scrollable"
        tabIndex={0}
        className="overflow-x-auto rounded-lg border border-border bg-card outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <table className="w-full min-w-[1100px] text-left text-sm">
          <caption className="sr-only">
            Current canonical job listings, ordered by last seen from newest to
            oldest.
          </caption>
          <thead className="border-b border-border bg-muted/40">
            <tr>
              {[
                "Job",
                "Company",
                "Location",
                "Type",
                "Lifecycle",
                "Last Seen",
                "Version",
              ].map((label) => (
                <th
                  key={label}
                  scope="col"
                  className="whitespace-nowrap px-4 py-3 text-xs font-medium text-muted-foreground"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="border-t border-border align-top">
                <td className="w-[270px] min-w-[220px] max-w-[300px] px-4 py-4">
                  <Link
                    href={`/dashboard/jobs/${job.id}`}
                    prefetch={false}
                    className="break-words font-medium text-foreground underline-offset-4 outline-none hover:text-primary hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {job.current_version.title}
                  </Link>
                  <p className="mt-1.5 break-all font-mono text-xs text-muted-foreground">
                    {job.external_job_id}
                  </p>
                </td>
                <td className="max-w-[180px] px-4 py-4">
                  <Link
                    href={`/dashboard/sources/${job.source.id}`}
                    prefetch={false}
                    className="break-words underline-offset-4 outline-none hover:text-primary hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {job.company.name}
                  </Link>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {getSourceProviderLabel(job.source.provider)}
                  </p>
                </td>
                <td className="max-w-[180px] px-4 py-4">
                  <p className="break-words">
                    {job.current_version.location_text || "—"}
                  </p>
                </td>
                <td className="whitespace-nowrap px-4 py-4">
                  <p>
                    {formatWorkplaceType(job.current_version.workplace_type)}
                  </p>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {formatEmploymentType(job.current_version.employment_type)}
                  </p>
                </td>
                <td className="min-w-[185px] px-4 py-4">
                  <LifecycleBadge status={job.lifecycle_status} />
                  {job.lifecycle_status === "observed" &&
                    job.absence_first_detected_at && (
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        Absence detected
                        <br />
                        <time dateTime={job.absence_first_detected_at}>
                          {formatAbsoluteTimestamp(
                            job.absence_first_detected_at,
                          )}
                        </time>
                      </p>
                    )}
                  {job.reappeared_at && (
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">
                      Reappeared
                      <br />
                      <time dateTime={job.reappeared_at}>
                        {formatAbsoluteTimestamp(job.reappeared_at)}
                      </time>
                    </p>
                  )}
                </td>
                <td className="min-w-[180px] px-4 py-4">
                  <time
                    dateTime={job.last_seen_at}
                    className="text-xs leading-5"
                  >
                    {formatAbsoluteTimestamp(job.last_seen_at)}
                  </time>
                  <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                    First seen
                    <br />
                    <time dateTime={job.first_seen_at}>
                      {formatAbsoluteTimestamp(job.first_seen_at)}
                    </time>
                  </p>
                </td>
                <td className="px-4 py-4 text-xs tabular-nums">
                  v{job.current_version.version_number}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
