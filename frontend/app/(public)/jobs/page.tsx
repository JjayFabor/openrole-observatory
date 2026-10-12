import type { Metadata } from "next";
import { buildJobsMetadata } from "@/lib/seo/metadata";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { listPublicJobs } from "@/lib/api/public-jobs";
import type { PublicJobListResponse } from "@/lib/api/public-jobs-types";
import { PublicJobCard } from "@/components/public/jobs/public-job-card";
import { PublicJobsFilters } from "@/components/public/jobs/public-jobs-filters";
import { PublicJobsPagination } from "@/components/public/jobs/public-jobs-pagination";
import {
  buildPublicJobsHref,
  getPublicJobsPageCount,
  hasPublicJobsFilters,
  needsPublicJobsNormalization,
  parsePublicJobsQuery,
  type PublicJobsSearchParams,
} from "@/lib/public-jobs/query-state";

export async function generateMetadata({ searchParams }: {
  searchParams: Promise<PublicJobsSearchParams>;
}): Promise<Metadata> {
  const query = parsePublicJobsQuery(await searchParams);
  return buildJobsMetadata(hasPublicJobsFilters(query) || query.page > 1);
}

export const dynamic = "force-dynamic";

export default async function PublicJobs({
  searchParams,
}: {
  searchParams: Promise<PublicJobsSearchParams>;
}) {
  const rawQuery = await searchParams;
  const query = parsePublicJobsQuery(rawQuery);
  const href = buildPublicJobsHref(query);
  if (needsPublicJobsNormalization(rawQuery, query)) redirect(href);

  let results: PublicJobListResponse | undefined;
  try {
    results = await listPublicJobs(query);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }
  if (results && query.page > getPublicJobsPageCount(results.total)) {
    redirect(
      buildPublicJobsHref(query, {
        page: getPublicJobsPageCount(results.total),
      }),
    );
  }

  return (
    <div className="py-10 sm:py-12">
      <header className="mb-8 max-w-3xl">
        <h1 className="text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          Find jobs with visible source freshness.
        </h1>
        <p className="mt-4 text-base leading-7 text-muted-foreground">
          Listings observed directly from configured employer ATS sources.
        </p>
      </header>
      <PublicJobsFilters key={href} query={query} />
      {!results ? (
        <section role="status" className="py-10">
          <h2 className="text-xl font-semibold">
            We couldn’t load jobs right now.
          </h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Please try again in a moment. Your search and filters are kept
            above.
          </p>
          <a
            href={href}
            className="mt-5 inline-block rounded-sm text-sm font-medium text-primary underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Try again
          </a>
        </section>
      ) : (
        <section aria-labelledby="jobs-results-heading" className="mt-8">
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border pb-4">
            <h2 id="jobs-results-heading" className="text-base font-semibold">
              {results.total.toLocaleString("en-US")}{" "}
              {results.total === 1 ? "job" : "jobs"} found
            </h2>
            <p className="text-xs leading-5 text-muted-foreground">
              Most recently observed first
            </p>
          </div>
          {results.items.length ? (
            <ul className="divide-y divide-border">
              {results.items.map((job) => (
                <li key={job.id} className="min-w-0">
                  <PublicJobCard job={job} />
                </li>
              ))}
            </ul>
          ) : (
            <div className="py-10">
              <h3 className="text-lg font-semibold">
                {results.total > 0
                  ? "No jobs on this page."
                  : hasPublicJobsFilters(query)
                    ? "No jobs match these filters."
                    : "No listings are available yet."}
              </h3>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                {results.total > 0
                  ? "Listings may have changed while you were browsing. Try the first page."
                  : hasPublicJobsFilters(query)
                    ? "Try a broader search, or clear filters to browse available listings."
                    : "Check back later for listings observed at configured employer sources."}
              </p>
              <a
                href={
                  results.total > 0
                    ? buildPublicJobsHref(query, { page: 1 })
                    : "/jobs"
                }
                className="mt-5 inline-block rounded-sm text-sm font-medium text-primary underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                {results.total > 0
                  ? "Go to first page"
                  : hasPublicJobsFilters(query)
                    ? "Clear filters"
                    : "Check again"}
              </a>
            </div>
          )}
          <PublicJobsPagination query={query} total={results.total} />
          <p className="mt-6 max-w-3xl text-xs leading-5 text-muted-foreground">
            Observed means OpenRole saw the listing at its employer ATS source.
            It is source evidence, not confirmation that the employer is hiring.
          </p>
        </section>
      )}
    </div>
  );
}
