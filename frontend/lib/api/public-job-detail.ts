import "server-only";
import { cache } from "react";
import { ApiClient, ApiError } from "./client";
import { getPublicJob } from "./public-jobs";
import type { PublicJobDetail } from "./public-jobs-types";

export type PublicJobDetailResult =
  | { state: "available"; job: PublicJobDetail }
  | { state: "not_found" }
  | { state: "unavailable" };

export async function readPublicJobDetail(
  jobId: string,
  client = new ApiClient(),
): Promise<PublicJobDetailResult> {
  try {
    const job = await getPublicJob(jobId, client);
    return job ? { state: "available", job } : { state: "not_found" };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return { state: "unavailable" };
  }
}

// Share the metadata/page read within one server request, without retaining stale listings across requests.
export const getPublicJobDetail = cache(readPublicJobDetail);
