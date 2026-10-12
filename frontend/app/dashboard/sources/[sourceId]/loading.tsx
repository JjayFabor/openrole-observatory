import { Skeleton } from "@/components/ui/skeleton";

export default function SourceDetailLoading() {
  return (
    <section
      aria-busy="true"
      aria-label="Loading source details"
      className="space-y-6"
    >
      <span role="status" className="sr-only">
        Loading source identity, freshness, and operational history.
      </span>
      <Skeleton className="h-7 w-64 max-w-full" />
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-36 w-full" />
      <Skeleton className="h-48 w-full" />
    </section>
  );
}
