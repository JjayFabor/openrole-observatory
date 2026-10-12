import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SourceDetail } from "@/components/sources/source-detail";
import { getSourceDetail } from "@/lib/api/source-detail";
import { SourceSyncButton } from "@/components/sources/source-sync-button";
import { synchronizeSource } from "./actions";

export const metadata: Metadata = { title: "Source Detail" };
export const dynamic = "force-dynamic";

export default async function SourceDetailPage({
  params,
}: {
  params: Promise<{ sourceId: string }>;
}) {
  const { sourceId } = await params;
  const result = await getSourceDetail(sourceId);
  if (result.state === "not_found") notFound();
  return (
    <div>
      <Button variant="ghost" asChild className="-ml-3 mb-5">
        <Link href="/dashboard/sources">
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to sources
        </Link>
      </Button>
      {result.state === "available" ? (
        <SourceDetail
          source={result.source}
          runs={result.runs}
          quarantine={result.quarantine}
          now={result.fetchedAt}
          action={
            <SourceSyncButton
              sourceId={result.source.id}
              active={result.source.is_active}
              syncAction={synchronizeSource}
            />
          }
        />
      ) : (
        <section
          role="status"
          className="rounded-lg border border-border bg-card p-6"
        >
          <h1 className="text-xl font-semibold tracking-tight">
            Unable to load source.
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Source information is currently unavailable. Refresh the page to try
            again.
          </p>
        </section>
      )}
    </div>
  );
}
