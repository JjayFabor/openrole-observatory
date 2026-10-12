import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  buildPublicJobsHref,
  getPublicJobsPageCount,
  type PublicJobsQueryState,
} from "@/lib/public-jobs/query-state";

export function PublicJobsPagination({
  query,
  total,
}: {
  query: PublicJobsQueryState;
  total: number;
}) {
  const pageCount = getPublicJobsPageCount(total);
  return (
    <nav
      aria-label="Job results pagination"
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-t border-border pt-6"
    >
      {query.page > 1 ? (
        <Button asChild variant="outline" className="h-11">
          <Link href={buildPublicJobsHref(query, { page: query.page - 1 })}>
            Previous
          </Link>
        </Button>
      ) : (
        <span
          aria-disabled="true"
          className="inline-flex h-11 items-center px-3 text-sm text-muted-foreground"
        >
          Previous
        </span>
      )}
      <p className="text-sm text-muted-foreground">
        Page {query.page.toLocaleString("en-US")} of{" "}
        {pageCount.toLocaleString("en-US")}
      </p>
      {query.page < pageCount ? (
        <Button asChild variant="outline" className="h-11">
          <Link href={buildPublicJobsHref(query, { page: query.page + 1 })}>
            Next
          </Link>
        </Button>
      ) : (
        <span
          aria-disabled="true"
          className="inline-flex h-11 items-center px-3 text-sm text-muted-foreground"
        >
          Next
        </span>
      )}
    </nav>
  );
}
