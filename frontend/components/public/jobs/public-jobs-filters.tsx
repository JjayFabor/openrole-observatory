import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  formatEmploymentType,
  formatWorkplaceType,
} from "@/lib/jobs/presentation";
import {
  publicEmploymentOptions,
  publicWorkplaceOptions,
  type PublicJobsQueryState,
} from "@/lib/public-jobs/query-state";

const controlClassName =
  "mt-2 h-11 w-full min-w-0 rounded-md border border-border bg-card px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

export function PublicJobsFilters({ query }: { query: PublicJobsQueryState }) {
  return (
    <form
      action="/jobs"
      method="get"
      autoComplete="off"
      aria-label="Search and filter jobs"
      className="border-y border-border py-6"
    >
      <label className="block text-sm font-medium" htmlFor="jobs-search">
        Search jobs
      </label>
      <input
        id="jobs-search"
        name="q"
        type="search"
        maxLength={200}
        defaultValue={query.q ?? ""}
        placeholder="Search title, company, or location"
        className={controlClassName}
      />
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-end">
        <label
          className="block min-w-0 text-sm font-medium"
          htmlFor="jobs-location"
        >
          Location
          <input
            id="jobs-location"
            name="location"
            type="text"
            maxLength={200}
            defaultValue={query.location ?? ""}
            placeholder="e.g. Berlin or Remote"
            className={controlClassName}
          />
        </label>
        <label
          className="block min-w-0 text-sm font-medium"
          htmlFor="jobs-workplace"
        >
          Workplace
          <select
            id="jobs-workplace"
            name="workplace"
            defaultValue={query.workplace ?? ""}
            className={controlClassName}
          >
            <option value="">Any workplace</option>
            {publicWorkplaceOptions.map((value) => (
              <option key={value} value={value}>
                {formatWorkplaceType(value)}
              </option>
            ))}
          </select>
        </label>
        <label
          className="block min-w-0 text-sm font-medium"
          htmlFor="jobs-employment"
        >
          Employment type
          <select
            id="jobs-employment"
            name="employment"
            defaultValue={query.employment ?? ""}
            className={controlClassName}
          >
            <option value="">Any employment type</option>
            {publicEmploymentOptions.map((value) => (
              <option key={value} value={value}>
                {formatEmploymentType(value)}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" className="h-11 px-5">
            Search
          </Button>
          <Link
            href="/jobs"
            className="rounded-sm text-sm text-muted-foreground underline underline-offset-4 outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Clear filters
          </Link>
        </div>
      </div>
      <p className="mt-4 text-xs leading-5 text-muted-foreground">
        Location matches the listing’s location text. Filters narrow results
        together.
      </p>
    </form>
  );
}
