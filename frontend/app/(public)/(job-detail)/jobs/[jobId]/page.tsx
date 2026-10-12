import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import { getPublicJobDetail } from "@/lib/api/public-job-detail";
import { buildPublicJobMetadata } from "@/lib/public-jobs/detail-metadata";
import { buildUnavailableJobMetadata } from "@/lib/seo/metadata";
import { PublicJobDetail } from "@/components/public/jobs/public-job-detail";
import {
  PublicJobChangesSection,
  PublicJobChangesLoading,
} from "@/components/public/jobs/public-job-changes";
import { Button } from "@/components/ui/button";

type PublicJobPageProps = { params: Promise<{ jobId: string }> };

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: PublicJobPageProps): Promise<Metadata> {
  const { jobId } = await params;
  const result = await getPublicJobDetail(jobId);
  if (result.state === "not_found") notFound();
  if (result.state === "unavailable") {
    return buildUnavailableJobMetadata();
  }
  return buildPublicJobMetadata(result.job);
}

export default async function PublicJobPage({ params }: PublicJobPageProps) {
  const { jobId } = await params;
  const result = await getPublicJobDetail(jobId);
  if (result.state === "not_found") notFound();
  return (
    <div className="py-10 sm:py-12">
      <Button asChild variant="ghost" className="-ml-3 mb-7 h-11">
        <Link href="/jobs">← Back to jobs</Link>
      </Button>
      {result.state === "available" ? (
        <>
          <PublicJobDetail job={result.job} />
          <Suspense fallback={<PublicJobChangesLoading />}>
            <PublicJobChangesSection jobId={jobId} />
          </Suspense>
        </>
      ) : (
        <section role="status" className="py-6">
          <h1 className="text-2xl font-semibold tracking-tight">
            We couldn’t load this job right now.
          </h1>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            Please try again in a moment.
          </p>
          <a
            href={`/jobs/${jobId}`}
            className="mt-5 inline-block rounded-sm text-sm font-medium text-primary underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Try again
          </a>
        </section>
      )}
    </div>
  );
}
