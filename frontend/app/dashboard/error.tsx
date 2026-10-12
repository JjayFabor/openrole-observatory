"use client";

import { RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function DashboardError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section
      role="alert"
      className="rounded-lg border border-border bg-card p-6 sm:p-8"
    >
      <h1 className="text-xl font-semibold tracking-tight">
        Unable to load dashboard data.
      </h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        Please try again in a moment.
      </p>
      <Button variant="outline" className="mt-5" onClick={reset}>
        <RotateCw className="size-4" aria-hidden="true" />
        Try again
      </Button>
    </section>
  );
}
