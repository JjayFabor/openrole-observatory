import { Skeleton } from "@/components/ui/skeleton";

export default function JobsLoading() {
  return (
    <section
      aria-busy="true"
      aria-label="Loading jobs"
      className="py-10 sm:py-12"
    >
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        Find jobs with visible source freshness.
      </h1>
      <p role="status" className="mt-4 text-sm text-muted-foreground">
        Loading jobs…
      </p>
      <div aria-hidden="true" className="mt-8">
        <Skeleton className="h-11 w-full" />
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-11" />
          <Skeleton className="h-11" />
          <Skeleton className="h-11" />
        </div>
        <div className="mt-8 divide-y divide-border">
          {[0, 1, 2].map((item) => (
            <div key={item} className="py-7">
              <Skeleton className="h-6 w-2/3 max-w-sm" />
              <Skeleton className="mt-3 h-4 w-1/3 max-w-48" />
              <Skeleton className="mt-3 h-4 w-1/2 max-w-64" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
