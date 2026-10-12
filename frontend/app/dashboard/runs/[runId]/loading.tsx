import { Skeleton } from "@/components/ui/skeleton";
export default function RunDetailLoading() {
  return (
    <div aria-label="Loading pipeline run" className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-6 w-72 max-w-full" />
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}
