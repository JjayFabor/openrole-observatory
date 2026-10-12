import type { Metadata } from "next";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { RunFilters } from "@/components/runs/run-filters";
import { RunsTable } from "@/components/runs/runs-table";
import { RunsPagination } from "@/components/runs/runs-pagination";
import { listRuns } from "@/lib/api/pipeline-runs";
import {
  buildRunsHref,
  parseRunsQuery,
  type RunsSearchParams,
} from "@/lib/runs/query-state";
export const metadata: Metadata = { title: "Pipeline Runs" };
export const dynamic = "force-dynamic";
export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<RunsSearchParams>;
}) {
  const state = parseRunsQuery(await searchParams);
  const result = await listRuns(state).then(
    (data) => ({ state: "available" as const, data }),
    () => ({ state: "unavailable" as const }),
  );
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Pipeline Runs</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Inspect ingestion attempts, metrics, and failures.
        </p>
      </header>
      <RunFilters key={buildRunsHref(state)} state={state} />
      {state.source && (
        <p className="break-all text-xs leading-5 text-muted-foreground">
          Source scope:{" "}
          <Link
            href={`/dashboard/sources/${state.source}`}
            className="font-mono text-primary underline underline-offset-4 outline-none focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
          >
            {state.source}
          </Link>
        </p>
      )}
      {result.state === "unavailable" ? (
        <div
          role="status"
          className="rounded-lg border border-border bg-card p-6"
        >
          <h2 className="text-base font-medium">
            Unable to load pipeline runs.
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Pipeline information is currently unavailable. Refresh the page to
            try again.
          </p>
        </div>
      ) : (
        <>
          {result.data.items.length > 0 ? (
            <>
              <p className="text-xs text-muted-foreground">
                Newest attempts first · Up to 25 runs
              </p>
              <RunsTable runs={result.data.items} />
            </>
          ) : (
            <div className="rounded-lg border border-border bg-card p-6">
              <h2 className="text-base font-medium">
                {state.page > 1
                  ? "No pipeline runs on this page."
                  : state.status || state.source
                    ? "No pipeline runs match these filters."
                    : "No pipeline runs yet."}
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {state.page > 1
                  ? "Try the first page of these results."
                  : state.status || state.source
                    ? "Clear filters to inspect all source synchronization attempts."
                    : "Source synchronization attempts will appear here."}
              </p>
              {state.page > 1 && (
                <Button variant="outline" asChild className="mt-4">
                  <Link href={buildRunsHref(state, { page: 1 })}>
                    Go to first page
                  </Link>
                </Button>
              )}
              {state.page === 1 && (state.status || state.source) && (
                <Button variant="outline" asChild className="mt-4">
                  <Link href="/dashboard/runs">Clear filters</Link>
                </Button>
              )}
            </div>
          )}
          <RunsPagination state={state} hasNext={result.data.hasNext} />
        </>
      )}
    </section>
  );
}
