import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  buildSourcesHref,
  MAX_SOURCES_PAGE,
  SOURCES_PAGE_SIZE,
  type SourcesQueryState,
} from "@/lib/sources/query-state";

export function SourcePagination({
  state,
  total,
}: {
  state: SourcesQueryState;
  total: number;
}) {
  const pages = Math.min(
    MAX_SOURCES_PAGE,
    Math.max(1, Math.ceil(total / SOURCES_PAGE_SIZE)),
  );
  const previous = total > 0 && state.page > 1;
  const next = total > 0 && state.page < pages;
  return (
    <nav
      aria-label="Sources pagination"
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
              href={buildSourcesHref(state, { page: state.page - 1 })}
              aria-label="Previous sources page"
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
              href={buildSourcesHref(state, { page: state.page + 1 })}
              aria-label="Next sources page"
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
