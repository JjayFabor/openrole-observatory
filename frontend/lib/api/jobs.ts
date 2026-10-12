import "server-only";
import { ApiClient, ApiError } from "./client";
import type { JobListItem, JobListResponse } from "./types";
import {
  isCounter,
  isNullableTimestamp,
  isRecord,
  isTimestamp,
  isUuid,
} from "./validation";
import {
  JOBS_PAGE_SIZE,
  parseJobsQuery,
  type JobsQueryState,
} from "../jobs/query-state";

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isJobListItem(value: unknown): value is JobListItem {
  if (
    !isRecord(value) ||
    !isRecord(value.company) ||
    !isRecord(value.source) ||
    !isRecord(value.current_version)
  )
    return false;
  const version = value.current_version;
  return (
    isUuid(value.id) &&
    typeof value.external_job_id === "string" &&
    isUuid(value.company.id) &&
    typeof value.company.name === "string" &&
    isUuid(value.source.id) &&
    value.source.provider === "greenhouse" &&
    (value.lifecycle_status === "observed" ||
      value.lifecycle_status === "not_observed") &&
    isTimestamp(value.first_seen_at) &&
    isTimestamp(value.last_seen_at) &&
    isNullableTimestamp(value.absence_first_detected_at) &&
    isNullableTimestamp(value.reappeared_at) &&
    isCounter(value.consecutive_absent_runs) &&
    isUuid(version.id) &&
    isCounter(version.version_number) &&
    version.version_number > 0 &&
    typeof version.title === "string" &&
    isNullableString(version.location_text) &&
    isNullableString(version.workplace_type) &&
    isNullableString(version.employment_type)
  );
}

export async function listJobs(
  state: JobsQueryState,
  client = new ApiClient(),
): Promise<JobListResponse> {
  const query = parseJobsQuery({
    page: String(state.page),
    status: state.status,
    source: state.source,
    q: state.q,
  });
  const offset = (query.page - 1) * JOBS_PAGE_SIZE;
  const params = new URLSearchParams({
    limit: String(JOBS_PAGE_SIZE),
    offset: String(offset),
  });
  if (query.status) params.set("lifecycle_status", query.status);
  if (query.source) params.set("source_connection_id", query.source);
  if (query.q) params.set("q", query.q);
  const { status, body } = await client.getJson(`/api/v1/jobs?${params}`);
  if (
    status !== 200 ||
    !isRecord(body) ||
    body.limit !== JOBS_PAGE_SIZE ||
    body.offset !== offset ||
    !isCounter(body.total) ||
    !Array.isArray(body.items) ||
    body.items.length > JOBS_PAGE_SIZE ||
    body.items.length > body.total ||
    !body.items.every(isJobListItem)
  ) {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  return {
    items: body.items,
    total: body.total,
    limit: body.limit,
    offset: body.offset,
  };
}
