import Link from "next/link";
import { Button } from "@/components/ui/button";
import { pipelineStatuses } from "@/lib/api/types";
import { getPipelineStatusPresentation } from "@/lib/dashboard/presentation";
import type { RunsQueryState } from "@/lib/runs/query-state";

export function RunFilters({ state }: { state: RunsQueryState }) {
  return (
    <form
      action="/dashboard/runs"
      method="get"
      className="rounded-lg border border-border bg-card p-4 sm:p-5"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="lg:w-52 lg:shrink-0">
          <label
            htmlFor="run-status"
            className="mb-2 block text-xs font-medium"
          >
            Run status
          </label>
          <select
            id="run-status"
            name="status"
            defaultValue={state.status ?? ""}
            className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All statuses</option>
            {pipelineStatuses.map((status) => (
              <option key={status} value={status}>
                {getPipelineStatusPresentation(status).label}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 flex-1">
          <label
            htmlFor="run-source"
            className="mb-2 block text-xs font-medium"
          >
            Source UUID (optional)
          </label>
          <input
            id="run-source"
            name="source"
            type="text"
            maxLength={36}
            defaultValue={state.source ?? ""}
            aria-describedby="run-source-hint"
            placeholder="All sources"
            className="h-9 w-full rounded-md border border-border bg-background px-3 font-mono text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="submit">Apply filters</Button>
          <Button variant="outline" asChild>
            <Link href="/dashboard/runs">Clear filters</Link>
          </Button>
        </div>
      </div>
      <p
        id="run-source-hint"
        className="mt-3 text-xs leading-5 text-muted-foreground"
      >
        Use an existing identifier from{" "}
        <Link
          href="/dashboard/sources"
          className="text-primary underline underline-offset-4 outline-none focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
        >
          Sources
        </Link>
        , or leave blank to inspect all sources.
      </p>
    </form>
  );
}
