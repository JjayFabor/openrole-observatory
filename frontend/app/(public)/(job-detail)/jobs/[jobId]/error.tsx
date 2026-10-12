"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function PublicJobError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section role="alert" className="py-12 sm:py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        We couldn’t load this job right now.
      </h1>
      <p className="mt-4 text-sm leading-6 text-muted-foreground">
        Please try again in a moment.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Button type="button" className="h-11 px-5" onClick={reset}>
          Try again
        </Button>
        <Button asChild variant="outline" className="h-11 px-5">
          <Link href="/jobs">Back to jobs</Link>
        </Button>
      </div>
    </section>
  );
}
