import { Skeleton } from "@/components/ui/skeleton";

export default function SourcesLoading() {
  return (
    <section
      aria-busy="true"
      aria-label="Loading sources"
      className="space-y-6"
    >
      <span role="status" className="sr-only">
        Loading configured ATS sources.
      </span>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Sources</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          ATS sources monitored by OpenRole.
        </p>
      </header>
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
