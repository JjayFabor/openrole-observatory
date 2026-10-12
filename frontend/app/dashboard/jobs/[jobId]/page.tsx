import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { JobDetail } from "@/components/jobs/job-detail";
import { getJobDetail } from "@/lib/api/job-detail";
import {
  parseJobHistoryQuery,
  type HistorySearchParams,
} from "@/lib/jobs/history-query";
export const metadata: Metadata = { title: "Job Detail" };
export const dynamic = "force-dynamic";
export default async function JobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ jobId: string }>;
  searchParams: Promise<HistorySearchParams>;
}) {
  const { jobId } = await params;
  const query = parseJobHistoryQuery(await searchParams);
  const detail = await getJobDetail(jobId, query);
  if (detail.state === "not_found") notFound();
  return (
    <div>
      <Button variant="ghost" asChild className="-ml-3 mb-5">
        <Link href="/dashboard/jobs">
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to jobs
        </Link>
      </Button>
      {detail.state === "available" ? (
        <JobDetail detail={detail} query={query} />
      ) : (
        <section
          role="status"
          className="rounded-lg border border-border bg-card p-6"
        >
          <h1 className="text-xl font-semibold">Unable to load job.</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Job information is currently unavailable. Refresh the page to try
            again.
          </p>
        </section>
      )}
    </div>
  );
}
