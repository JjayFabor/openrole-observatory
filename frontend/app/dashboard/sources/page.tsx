import type { Metadata } from "next";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SourceFilters } from "@/components/sources/source-filters";
import { SourcePagination } from "@/components/sources/source-pagination";
import { SourceTable } from "@/components/sources/source-table";
import { listSources } from "@/lib/api/sources";
import {
  buildSourcesHref,
  getSourcesEmptyState,
  parseSourcesQuery,
  type SourcesSearchParams,
} from "@/lib/sources/query-state";

export const metadata: Metadata = { title: "Sources" };
export const dynamic = "force-dynamic";

export default async function SourcesPage({
  searchParams,
}: {
  searchParams: Promise<SourcesSearchParams>;
}) {
  const state = parseSourcesQuery(await searchParams);
  const result = await listSources(state).then(
    (data) => ({ state: "available" as const, data }),
    () => ({ state: "unavailable" as const }),
  );
  const empty =
    result.state === "available"
      ? getSourcesEmptyState(result.data.total, state)
      : undefined;
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Sources</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          ATS sources monitored by OpenRole.
        </p>
      </header>
      <SourceFilters key={buildSourcesHref(state)} state={state} />
      {result.state === "unavailable" ? (
        <div
          role="status"
          className="rounded-lg border border-border bg-card p-6"
        >
          <h2 className="text-base font-medium">Unable to load sources.</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Source information is currently unavailable. Refresh the page to try
            again.
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium">
              {result.data.total.toLocaleString("en-US")}{" "}
              {result.data.total === 1 ? "source" : "sources"}
            </h2>
            <p className="text-xs text-muted-foreground">Ordered by company</p>
          </div>
          {result.data.items.length ? (
            <SourceTable sources={result.data.items} />
          ) : (
            <div className="rounded-lg border border-border bg-card p-6">
              <h3 className="text-base font-medium">
                {empty === "page"
                  ? "No sources on this page."
                  : empty === "filtered"
                    ? "No sources match this filter."
                    : "No sources configured."}
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {empty === "page"
                  ? "Try the first page of these results."
                  : empty === "filtered"
                    ? "Clear the filter to see all configured sources."
                    : "Configured ATS sources will appear here."}
              </p>
              {empty === "page" && (
                <Button variant="outline" asChild className="mt-4">
                  <Link href={buildSourcesHref(state, { page: 1 })}>
                    Go to first page
                  </Link>
                </Button>
              )}
              {empty === "filtered" && (
                <Button variant="outline" asChild className="mt-4">
                  <Link href="/dashboard/sources">Clear filter</Link>
                </Button>
              )}
            </div>
          )}
          <SourcePagination state={state} total={result.data.total} />
        </>
      )}
      <p className="max-w-3xl text-xs leading-5 text-muted-foreground">
        Active state describes source configuration. The latest run status
        describes a synchronization attempt.
      </p>
    </section>
  );
}
