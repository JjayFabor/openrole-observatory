"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  buildQuarantineHref,
  hasQuarantineFilters,
  type QuarantineQueryState,
} from "@/lib/quarantine/query-state";
import { quarantineCategories } from "@/lib/quarantine/presentation";

export function QuarantineFilters({ state }: { state: QuarantineQueryState }) {
  const router = useRouter();
  const [status, setStatus] = useState(state.status ?? "");
  const [category, setCategory] = useState(state.category ?? "");
  const [pending, startTransition] = useTransition();
  const customCategory =
    state.category &&
    !quarantineCategories.some((known) => known.value === state.category)
      ? state.category
      : undefined;

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const href = buildQuarantineHref(state, {
      page: 1,
      status: status === "open" || status === "resolved" ? status : undefined,
      category: category || undefined,
    });
    startTransition(() => router.push(href));
  }

  return (
    <form
      onSubmit={applyFilters}
      aria-label="Filter quarantined records"
      aria-busy={pending}
      className="rounded-lg border border-border bg-card p-4 sm:p-5"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="lg:w-44">
          <label
            htmlFor="quarantine-status"
            className="mb-2 block text-xs font-medium"
          >
            Status
          </label>
          <select
            id="quarantine-status"
            name="status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
        <div className="min-w-0 flex-1">
          <label
            htmlFor="quarantine-category"
            className="mb-2 block text-xs font-medium"
          >
            Error category
          </label>
          <select
            id="quarantine-category"
            name="category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All categories</option>
            {quarantineCategories.map((known) => (
              <option key={known.value} value={known.value}>
                {known.label}
              </option>
            ))}
            {customCategory && (
              <option value={customCategory}>{customCategory}</option>
            )}
          </select>
        </div>
        <Button type="submit" disabled={pending}>
          {pending ? "Applying…" : "Apply filters"}
        </Button>
        {hasQuarantineFilters(state) && (
          <Button variant="outline" asChild>
            <Link href="/dashboard/quarantine">Clear filters</Link>
          </Button>
        )}
      </div>
      <span className="sr-only" role="status">
        {pending ? "Applying quarantine filters." : ""}
      </span>
    </form>
  );
}
