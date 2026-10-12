import "server-only";
import { ApiClient, ApiError } from "./client";
import {
  getJob,
  getJobChanges,
  getJobLifecycle,
  getJobVersions,
} from "./job-history";
import { getSource } from "./sources";
import { isUuid } from "./validation";
import type {
  InspectionSection,
  JobDetailRead,
  JobDetailResult,
} from "./types";
import type { JobHistoryQuery } from "../jobs/history-query";

function settledSection<T>(
  result: PromiseSettledResult<T>,
): InspectionSection<T> {
  return result.status === "fulfilled"
    ? { state: "available", data: result.value }
    : { state: "unavailable" };
}
export async function getJobDetail(
  jobId: string,
  query: JobHistoryQuery,
  client = new ApiClient(),
): Promise<JobDetailResult> {
  if (!isUuid(jobId)) return { state: "not_found" };
  let job: JobDetailRead;
  try {
    job = await getJob(jobId, client);
  } catch (error) {
    return {
      state:
        error instanceof ApiError && error.status === 404
          ? "not_found"
          : "unavailable",
    };
  }
  const [source, versions, changes, lifecycle] = await Promise.allSettled([
    getSource(job.source_connection_id, client).then((value) => {
      if (value.company_id.toLowerCase() !== job.company_id.toLowerCase())
        throw new ApiError(200, "INVALID_RESPONSE");
      return value;
    }),
    getJobVersions(jobId, query.versions, client),
    getJobChanges(jobId, query.changes, client),
    getJobLifecycle(jobId, query.lifecycle, client),
  ]);
  return {
    state: "available",
    job,
    source: settledSection(source),
    versions: settledSection(versions),
    changes: settledSection(changes),
    lifecycle: settledSection(lifecycle),
  };
}
