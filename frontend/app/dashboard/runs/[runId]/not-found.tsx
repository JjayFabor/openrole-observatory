import Link from "next/link";
import { Button } from "@/components/ui/button";
export default function RunNotFound() {
  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">
        Pipeline run not found.
      </h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        This run does not exist or its identifier is invalid.
      </p>
      <Button variant="outline" asChild className="mt-5">
        <Link href="/dashboard/runs">Back to pipeline runs</Link>
      </Button>
    </section>
  );
}
