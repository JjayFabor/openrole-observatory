"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  buildJobsHref,
  hasJobsFilters,
  type JobsQueryState,
} from "@/lib/jobs/query-state";

export function JobsFilters({ state }: { state: JobsQueryState }) {
  const router = useRouter();
  const [search, setSearch] = useState(state.q ?? "");
  const [status, setStatus] = useState(state.status ?? "");
  const [pending, startTransition] = useTransition();

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const href = buildJobsHref(state, {
      page: 1,
      q: search,
      status:
        status === "observed" || status === "not_observed" ? status : undefined,
    });
    startTransition(() => router.push(href));
  }

  return (
    <form
      onSubmit={applyFilters}
      aria-label="Filter jobs"
      aria-busy={pending}
      className="rounded-lg border border-border bg-card p-4 sm:p-5"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="min-w-0 flex-1">
          <label
            htmlFor="jobs-search"
            className="mb-2 block text-xs font-medium"
          >
            Search
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              id="jobs-search"
              name="q"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              maxLength={200}
              placeholder="Title, location, or external ID"
              className="h-9 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
        </div>
        <div className="lg:w-44">
          <label
            htmlFor="jobs-status"
            className="mb-2 block text-xs font-medium"
          >
            Lifecycle
          </label>
          <select
            id="jobs-status"
            name="status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All statuses</option>
            <option value="observed">Observed</option>
            <option value="not_observed">Not observed</option>
          </select>
        </div>
        <Button type="submit" disabled={pending} className="shrink-0">
          {pending ? "Applying…" : "Apply filters"}
        </Button>
        {hasJobsFilters(state) && (
          <Button variant="outline" asChild>
            <Link href="/dashboard/jobs">Clear filters</Link>
          </Button>
        )}
      </div>
      <span className="sr-only" role="status">
        {pending ? "Applying job filters." : ""}
      </span>
    </form>
  );
}
