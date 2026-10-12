import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function QuarantineNotFound() {
  return (
    <section>
      <p className="text-xs font-medium text-muted-foreground">404</p>
      <h1 className="mt-3 text-2xl font-semibold tracking-tight">
        Quarantined record not found.
      </h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        This record is not available for inspection.
      </p>
      <Button variant="outline" asChild className="mt-5">
        <Link href="/dashboard/quarantine">Back to quarantine</Link>
      </Button>
    </section>
  );
}
