import { Skeleton } from "@/components/ui/skeleton";

export default function JobLoading() {
  return (
    <section
      aria-busy="true"
      aria-label="Loading job"
      className="py-12 sm:py-16"
    >
      <h1 className="text-2xl font-semibold tracking-tight">Loading job</h1>
      <p role="status" className="mt-4 text-sm text-muted-foreground">
        Loading job…
      </p>
      <div aria-hidden="true" className="mt-6">
        <Skeleton className="h-9 w-2/3 max-w-xl" />
        <Skeleton className="mt-4 h-5 w-1/3 max-w-48" />
        <Skeleton className="mt-6 h-11 w-48" />
        <div className="mt-10 grid gap-8 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <div>
            <Skeleton className="h-5 w-32" />
            <Skeleton className="mt-4 h-4 w-44" />
            <Skeleton className="mt-4 h-4 w-40" />
          </div>
          <div>
            <Skeleton className="h-6 w-40" />
            <Skeleton className="mt-5 h-4 w-full" />
            <Skeleton className="mt-4 h-4 w-full" />
            <Skeleton className="mt-4 h-4 w-3/4" />
          </div>
        </div>
      </div>
    </section>
  );
}
