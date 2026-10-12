import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardLoading() {
  return (
    <section
      aria-busy="true"
      aria-label="Loading dashboard overview"
      className="space-y-8"
    >
      <span className="sr-only" role="status">
        Loading system status, source health, and recent pipeline runs.
      </span>
      <div>
        <Skeleton className="h-7 w-36" />
        <Skeleton className="mt-3 h-4 w-80 max-w-full" />
      </div>
      {[
        ["System Status", "h-20"],
        ["Source Health", "h-52"],
        ["Recent Pipeline Runs", "h-40"],
      ].map(([label, height]) => (
        <div key={label}>
          <h2 className="mb-3 text-base font-semibold">{label}</h2>
          <Skeleton className={`${height} w-full border border-border`} />
        </div>
      ))}
    </section>
  );
}
