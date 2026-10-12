import { Skeleton } from "@/components/ui/skeleton";

export default function JobsLoading() {
  return (
    <section aria-busy="true" aria-label="Loading jobs" className="space-y-6">
      <span className="sr-only" role="status">
        Loading current job listings.
      </span>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Listings observed directly from configured ATS sources.
        </p>
      </div>
      <Skeleton className="h-24 w-full" />
      <div className="space-y-3 rounded-lg border border-border bg-card p-5">
        <Skeleton className="h-8 w-full" />
        {[0, 1, 2, 3, 4].map((row) => (
          <Skeleton key={row} className="h-16 w-full" />
        ))}
      </div>
    </section>
  );
}
