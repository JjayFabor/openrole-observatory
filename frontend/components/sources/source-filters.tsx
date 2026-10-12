"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  buildSourcesHref,
  type SourcesQueryState,
} from "@/lib/sources/query-state";

export function SourceFilters({ state }: { state: SourcesQueryState }) {
  const router = useRouter();
  const [active, setActive] = useState(
    state.active === undefined ? "" : String(state.active),
  );
  const [pending, startTransition] = useTransition();

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const href = buildSourcesHref(state, {
      page: 1,
      active: active === "true" ? true : active === "false" ? false : undefined,
    });
    startTransition(() => router.push(href));
  }

  return (
    <form
      aria-label="Filter sources"
      aria-busy={pending}
      onSubmit={applyFilters}
      className="rounded-lg border border-border bg-card p-4 sm:p-5"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="lg:w-48">
          <label
            htmlFor="sources-active"
            className="mb-2 block text-xs font-medium"
          >
            Active state
          </label>
          <select
            id="sources-active"
            name="active"
            value={active}
            onChange={(event) => setActive(event.target.value)}
            className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All sources</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
        <Button type="submit" disabled={pending}>
          {pending ? "Applying…" : "Apply filter"}
        </Button>
        {state.active !== undefined && (
          <Button variant="outline" asChild>
            <Link href="/dashboard/sources">Clear filter</Link>
          </Button>
        )}
      </div>
      <span role="status" className="sr-only">
        {pending ? "Applying source filter." : ""}
      </span>
    </form>
  );
}
