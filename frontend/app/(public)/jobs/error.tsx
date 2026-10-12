"use client";

import { Button } from "@/components/ui/button";

export default function JobsError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section role="alert" className="py-16">
      <h1 className="text-3xl font-semibold tracking-tight">
        We couldn’t load jobs right now.
      </h1>
      <p className="mt-4 text-sm leading-6 text-muted-foreground">
        Please try again in a moment.
      </p>
      <Button type="button" onClick={reset} className="mt-6 h-11 px-5">
        Try again
      </Button>
    </section>
  );
}
