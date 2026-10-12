import Link from "next/link";
import type { PublicJobListItem } from "@/lib/api/public-jobs-types";
import { formatAbsoluteTimestamp } from "@/lib/dashboard/presentation";
import { getSourceProviderLabel } from "@/lib/sources/presentation";
import {
  getPublicJobSalary,
  getPublicJobTypes,
} from "@/lib/public-jobs/presentation";

export function PublicJobCard({ job }: { job: PublicJobListItem }) {
  const types = getPublicJobTypes(job);
  const salary = getPublicJobSalary(job);
  return (
    <article className="grid min-w-0 gap-5 py-7 sm:grid-cols-[minmax(0,1fr)_15rem] sm:gap-8">
      <div className="min-w-0">
        <h3 className="text-xl font-semibold leading-7 tracking-tight [overflow-wrap:anywhere]">
          <Link
            href={`/jobs/${job.id}`}
            className="rounded-sm underline decoration-primary/30 underline-offset-4 outline-none hover:text-primary hover:decoration-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4"
          >
            {job.title}
          </Link>
        </h3>
        <p className="mt-2 text-base font-medium [overflow-wrap:anywhere]">
          {job.company.name}
        </p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
          {job.location_text?.trim()
            ? job.location_text
            : "Location not stated"}
        </p>
        {types && (
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {types}
          </p>
        )}
        {salary && (
          <p className="mt-2 text-sm font-medium leading-6 [overflow-wrap:anywhere]">
            {salary}
          </p>
        )}
      </div>
      <div className="min-w-0 sm:pt-1">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">
          Last observed
        </p>
        <time
          dateTime={job.last_seen_at}
          className="mt-2 block text-sm font-medium leading-6 [overflow-wrap:anywhere]"
        >
          {formatAbsoluteTimestamp(job.last_seen_at)}
        </time>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          Direct source · {getSourceProviderLabel(job.source.provider)}
        </p>
      </div>
    </article>
  );
}
