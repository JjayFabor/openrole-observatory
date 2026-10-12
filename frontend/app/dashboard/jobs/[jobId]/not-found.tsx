import Link from "next/link";
import { Button } from "@/components/ui/button";
export default function JobNotFound() {
  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">Job not found.</h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        This job does not exist or its identifier is invalid.
      </p>
      <Button variant="outline" asChild className="mt-5">
        <Link href="/dashboard/jobs">Back to jobs</Link>
      </Button>
    </section>
  );
}
