import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { QuarantineDetail } from "@/components/quarantine/quarantine-detail";
import { ApiError } from "@/lib/api/client";
import { getQuarantineRecord } from "@/lib/api/quarantine";
import { isUuid } from "@/lib/api/validation";

export const metadata: Metadata = { title: "Quarantined Record" };
export const dynamic = "force-dynamic";

export default async function QuarantineRecordPage({
  params,
}: {
  params: Promise<{ recordId: string }>;
}) {
  const { recordId } = await params;
  if (!isUuid(recordId)) notFound();
  const result = await getQuarantineRecord(recordId).then(
    (record) => ({ state: "available" as const, record }),
    (error: unknown) => ({
      state:
        error instanceof ApiError && error.status === 404
          ? ("not_found" as const)
          : ("unavailable" as const),
    }),
  );
  if (result.state === "not_found") notFound();
  return (
    <div>
      <Button variant="ghost" asChild className="-ml-3 mb-5">
        <Link href="/dashboard/quarantine">
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to quarantine
        </Link>
      </Button>
      {result.state === "available" ? (
        <QuarantineDetail record={result.record} />
      ) : (
        <section
          role="status"
          className="rounded-lg border border-border bg-card p-6"
        >
          <h1 className="text-xl font-semibold tracking-tight">
            Unable to load quarantined record.
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Record information is currently unavailable. Refresh the page to try
            again.
          </p>
        </section>
      )}
    </div>
  );
}
