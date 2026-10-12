import { Skeleton } from "@/components/ui/skeleton";

export default function QuarantineDetailLoading() {
  return (
    <section
      aria-busy="true"
      aria-label="Loading quarantined record"
      className="space-y-6"
    >
      <span role="status" className="sr-only">
        Loading processing error and record provenance.
      </span>
      <Skeleton className="h-7 w-60 max-w-full" />
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-36 w-full" />
    </section>
  );
}
