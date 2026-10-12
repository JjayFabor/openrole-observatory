import { notFound } from "next/navigation";
import { getPublicJobDetail } from "@/lib/api/public-job-detail";

export default async function PublicJobLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  const result = await getPublicJobDetail(jobId);
  // Resolve existence before the detail loading boundary can commit a successful response.
  if (result.state === "not_found") notFound();
  return <>{children}</>;
}
