import type { Metadata } from "next";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { JobsFilters } from "@/components/jobs/jobs-filters";
import { JobsPagination } from "@/components/jobs/jobs-pagination";
import { JobsTable } from "@/components/jobs/jobs-table";
import { listJobs } from "@/lib/api/jobs";
import {
  buildJobsHref,
  getJobsEmptyState,
  parseJobsQuery,
  type JobsSearchParams,
} from "@/lib/jobs/query-state";

export const metadata: Metadata = { title: "Jobs" };
export const dynamic = "force-dynamic";

export default async function JobsPage({
  searchParams,
}: {
  searchParams: Promise<JobsSearchParams>;
}) {
  const state = parseJobsQuery(await searchParams);
  const result = await listJobs(state).then(
    (data) => ({ state: "available" as const, data }),
    () => ({ state: "unavailable" as const }),
  );
  const empty =
    result.state === "available"
      ? getJobsEmptyState(result.data.total, state)
      : undefined;
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Listings observed directly from configured ATS sources.
        </p>
      </header>
      <JobsFilters key={buildJobsHref(state)} state={state} />
      {state.source && (
        <p className="break-all text-xs text-muted-foreground">
          Source scope: <span className="font-mono">{state.source}</span>
        </p>
      )}
      {result.state === "unavailable" ? (
        <div
          role="status"
          className="rounded-lg border border-border bg-card p-6"
        >
          <h2 className="text-base font-medium">Unable to load jobs.</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Job listings are currently unavailable. Refresh the page to try
            again.
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium">
              {result.data.total.toLocaleString("en-US")}{" "}
              {result.data.total === 1 ? "job" : "jobs"}
            </h2>
            <p className="text-xs text-muted-foreground">
              Most recently seen first
            </p>
          </div>
          {result.data.items.length ? (
            <JobsTable jobs={result.data.items} />
          ) : (
            <div className="rounded-lg border border-border bg-card p-6">
              <h3 className="text-base font-medium">
                {empty === "page"
                  ? "No jobs on this page."
                  : empty === "filtered"
                    ? "No jobs match your filters."
                    : "No jobs observed yet."}
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {empty === "page"
                  ? "Try the first page of these results."
                  : empty === "filtered"
                    ? "Try another search or clear the filters."
                    : "Listings will appear here after a source synchronization."}
              </p>
              {empty === "page" && (
                <Button variant="outline" className="mt-4" asChild>
                  <Link href={buildJobsHref(state, { page: 1 })}>
                    Go to first page
                  </Link>
                </Button>
              )}
              {empty === "filtered" && (
                <Button variant="outline" className="mt-4" asChild>
                  <Link href="/dashboard/jobs">Clear filters</Link>
                </Button>
              )}
            </div>
          )}
          <JobsPagination state={state} total={result.data.total} />
        </>
      )}
      <p className="max-w-3xl text-xs leading-5 text-muted-foreground">
        Observed and not observed describe OpenRole’s source observations; they
        do not confirm whether an employer has closed a listing.
      </p>
    </section>
  );
}
