import type { Metadata } from "next";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { QuarantineFilters } from "@/components/quarantine/quarantine-filters";
import { QuarantinePagination } from "@/components/quarantine/quarantine-pagination";
import { QuarantineTable } from "@/components/quarantine/quarantine-table";
import { listQuarantineRecords } from "@/lib/api/quarantine";
import {
  buildQuarantineHref,
  getQuarantineEmptyState,
  parseQuarantineQuery,
  type QuarantineSearchParams,
} from "@/lib/quarantine/query-state";

export const metadata: Metadata = { title: "Quarantine" };
export const dynamic = "force-dynamic";

export default async function QuarantinePage({
  searchParams,
}: {
  searchParams: Promise<QuarantineSearchParams>;
}) {
  const state = parseQuarantineQuery(await searchParams);
  const result = await listQuarantineRecords(state).then(
    (data) => ({ state: "available" as const, data }),
    () => ({ state: "unavailable" as const }),
  );
  const empty =
    result.state === "available"
      ? getQuarantineEmptyState(result.data.total, state)
      : undefined;
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Quarantine</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Records that could not be processed safely.
        </p>
      </header>
      <QuarantineFilters key={buildQuarantineHref(state)} state={state} />
      {(state.source || state.run) && (
        <div className="space-y-1 text-xs text-muted-foreground">
          {state.source && (
            <p className="break-all">
              Source scope: <span className="font-mono">{state.source}</span>
            </p>
          )}
          {state.run && (
            <p className="break-all">
              Pipeline run scope: <span className="font-mono">{state.run}</span>
            </p>
          )}
        </div>
      )}
      {result.state === "unavailable" ? (
        <div
          role="status"
          className="rounded-lg border border-border bg-card p-6"
        >
          <h2 className="text-base font-medium">
            Unable to load quarantined records.
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Record information is currently unavailable. Refresh the page to try
            again.
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium">
              {result.data.total.toLocaleString("en-US")}{" "}
              {result.data.total === 1 ? "record" : "records"}
            </h2>
            <p className="text-xs text-muted-foreground">Newest first</p>
          </div>
          {result.data.items.length ? (
            <QuarantineTable records={result.data.items} />
          ) : (
            <div className="rounded-lg border border-border bg-card p-6">
              <h3 className="text-base font-medium">
                {empty === "page"
                  ? "No quarantined records on this page."
                  : empty === "filtered"
                    ? "No quarantined records match these filters."
                    : "No quarantined records."}
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {empty === "page"
                  ? "Try the first page of these results."
                  : empty === "filtered"
                    ? "Try another category or clear the filters."
                    : "Source records that cannot be processed safely will appear here."}
              </p>
              {empty === "page" && (
                <Button variant="outline" asChild className="mt-4">
                  <Link href={buildQuarantineHref(state, { page: 1 })}>
                    Go to first page
                  </Link>
                </Button>
              )}
              {empty === "filtered" && (
                <Button variant="outline" asChild className="mt-4">
                  <Link href="/dashboard/quarantine">Clear filters</Link>
                </Button>
              )}
            </div>
          )}
          <QuarantinePagination state={state} total={result.data.total} />
        </>
      )}
      <p className="max-w-3xl text-xs leading-5 text-muted-foreground">
        Quarantine describes a record-level processing error. It does not
        establish that the entire pipeline run failed.
      </p>
    </section>
  );
}
