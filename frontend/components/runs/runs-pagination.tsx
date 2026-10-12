import Link from "next/link";
import { Button } from "@/components/ui/button";
import { buildRunsHref, type RunsQueryState } from "@/lib/runs/query-state";
import { MAX_HISTORY_PAGE } from "@/lib/jobs/history-query";

export function RunsPagination({
  state,
  hasNext,
}: {
  state: RunsQueryState;
  hasNext: boolean;
}) {
  return (
    <nav
      aria-label="Pipeline runs pagination"
      className="flex flex-wrap items-center justify-between gap-3"
    >
      <p className="text-xs tabular-nums text-muted-foreground">
        Page {state.page.toLocaleString("en-US")} · Up to 25 runs per page
      </p>
      <div className="flex gap-2">
        {state.page > 1 ? (
          <Button variant="outline" asChild>
            <Link href={buildRunsHref(state, { page: state.page - 1 })}>
              Previous
            </Link>
          </Button>
        ) : (
          <Button variant="outline" disabled>
            Previous
          </Button>
        )}
        {hasNext && state.page < MAX_HISTORY_PAGE ? (
          <Button variant="outline" asChild>
            <Link href={buildRunsHref(state, { page: state.page + 1 })}>
              Next
            </Link>
          </Button>
        ) : (
          <Button variant="outline" disabled>
            Next
          </Button>
        )}
      </div>
    </nav>
  );
}
