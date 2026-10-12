import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  buildJobsHref,
  JOBS_PAGE_SIZE,
  MAX_JOBS_PAGE,
  type JobsQueryState,
} from "@/lib/jobs/query-state";

export function JobsPagination({
  state,
  total,
}: {
  state: JobsQueryState;
  total: number;
}) {
  const pages = Math.min(
    MAX_JOBS_PAGE,
    Math.max(1, Math.ceil(total / JOBS_PAGE_SIZE)),
  );
  const previous = total > 0 && state.page > 1;
  const next = total > 0 && state.page < pages;
  return (
    <nav
      aria-label="Jobs pagination"
      className="flex flex-wrap items-center justify-between gap-4"
    >
      <p className="text-xs text-muted-foreground">
        Page{" "}
        <span className="font-medium text-foreground">
          {total === 0 ? 1 : state.page}
        </span>{" "}
        of {pages}
      </p>
      <div className="flex gap-2">
        {previous ? (
          <Button variant="outline" asChild>
            <Link
              href={buildJobsHref(state, { page: state.page - 1 })}
              aria-label="Previous jobs page"
            >
              <ChevronLeft className="size-4" aria-hidden="true" />
              Previous
            </Link>
          </Button>
        ) : (
          <Button variant="outline" disabled>
            <ChevronLeft className="size-4" aria-hidden="true" />
            Previous
          </Button>
        )}
        {next ? (
          <Button variant="outline" asChild>
            <Link
              href={buildJobsHref(state, { page: state.page + 1 })}
              aria-label="Next jobs page"
            >
              Next
              <ChevronRight className="size-4" aria-hidden="true" />
            </Link>
          </Button>
        ) : (
          <Button variant="outline" disabled>
            Next
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>
        )}
      </div>
    </nav>
  );
}
