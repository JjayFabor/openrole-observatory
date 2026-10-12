import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RunDetail } from "@/components/runs/run-detail";
import { getRunDetail } from "@/lib/api/run-detail";
import { buildRunsHref } from "@/lib/runs/query-state";
export const metadata: Metadata = { title: "Pipeline Run" };
export const dynamic = "force-dynamic";
export default async function PipelineRunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const detail = await getRunDetail(runId);
  if (detail.state === "not_found") notFound();
  return (
    <div>
      <Button variant="ghost" asChild className="-ml-3 mb-5">
        <Link
          href={
            detail.state === "available"
              ? buildRunsHref({
                  page: 1,
                  source: detail.run.source_connection_id,
                })
              : "/dashboard/runs"
          }
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to pipeline runs
        </Link>
      </Button>
      {detail.state === "available" ? (
        <RunDetail detail={detail} />
      ) : (
        <section
          role="status"
          className="rounded-lg border border-border bg-card p-6"
        >
          <h1 className="text-xl font-semibold">
            Unable to load pipeline run.
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Run information is currently unavailable. Refresh the page to try
            again.
          </p>
        </section>
      )}
    </div>
  );
}
