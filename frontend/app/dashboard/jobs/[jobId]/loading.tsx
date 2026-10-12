import { Skeleton } from "@/components/ui/skeleton";
export default function JobDetailLoading() {
  return (
    <div aria-label="Loading job detail" className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-6 w-64 max-w-full" />
      <div className="rounded-lg border border-border bg-card p-6">
        <Skeleton className="mb-5 h-5 w-32" />
        <div className="space-y-3">
          {Array.from({ length: 8 }, (_, index) => (
            <Skeleton key={index} className="h-4 w-full" />
          ))}
        </div>
      </div>
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}
