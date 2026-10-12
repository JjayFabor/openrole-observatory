import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  buildJobHistoryHref,
  MAX_HISTORY_PAGE,
  type JobHistoryQuery,
} from "@/lib/jobs/history-query";

export function JobHistoryPagination({
  jobId,
  state,
  section,
  hasNext,
}: {
  jobId: string;
  state: JobHistoryQuery;
  section: keyof JobHistoryQuery;
  hasNext: boolean;
}) {
  const page = state[section];
  return (
    <nav
      aria-label={`${section} pagination`}
      className="mt-4 flex flex-wrap items-center justify-between gap-3"
    >
      <p className="text-xs tabular-nums text-muted-foreground">
        Page {page.toLocaleString("en-US")} · Up to 25 records
      </p>
      <div className="flex gap-2">
        {page > 1 ? (
          <Button variant="outline" asChild>
            <Link href={buildJobHistoryHref(jobId, state, section, page - 1)}>
              Previous
            </Link>
          </Button>
        ) : (
          <Button variant="outline" disabled>
            Previous
          </Button>
        )}
        {hasNext && page < MAX_HISTORY_PAGE ? (
          <Button variant="outline" asChild>
            <Link href={buildJobHistoryHref(jobId, state, section, page + 1)}>
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
