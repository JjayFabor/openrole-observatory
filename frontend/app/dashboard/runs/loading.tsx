import { Skeleton } from "@/components/ui/skeleton";
export default function RunsLoading() {
  return (
    <div aria-label="Loading pipeline runs" className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-24 w-full" />
      <div className="rounded-lg border border-border bg-card p-6">
        <Skeleton className="mb-5 h-5 w-32" />
        <div className="space-y-4">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
