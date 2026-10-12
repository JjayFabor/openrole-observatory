import { Skeleton } from "@/components/ui/skeleton";

export default function QuarantineLoading() {
  return (
    <section
      aria-busy="true"
      aria-label="Loading quarantine records"
      className="space-y-6"
    >
      <span role="status" className="sr-only">
        Loading quarantined source records.
      </span>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Quarantine</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Records that could not be processed safely.
        </p>
      </header>
      <Skeleton className="h-24 w-full" />
      <div className="space-y-3 rounded-lg border border-border bg-card p-5">
        <Skeleton className="h-8 w-full" />
        {[0, 1, 2, 3, 4].map((row) => (
          <Skeleton key={row} className="h-20 w-full" />
        ))}
      </div>
    </section>
  );
}
