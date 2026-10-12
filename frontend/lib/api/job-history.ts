import "server-only";
import { ApiClient, ApiError } from "./client";
import type {
  HistoryPage,
  JobChangeEvent,
  JobDetailRead,
  JobLifecycleEvent,
  JobLifecycleRead,
  JobVersion,
  JsonObject,
  JsonValue,
} from "./types";
import {
  isCounter,
  isNullableTimestamp,
  isRecord,
  isTimestamp,
  isUuid,
} from "./validation";
import {
  HISTORY_PAGE_SIZE,
  HISTORY_READ_LIMIT,
  parseHistoryPage,
} from "../jobs/history-query";

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}
function isStatus(value: unknown): value is "observed" | "not_observed" {
  return value === "observed" || value === "not_observed";
}
function isJson(value: unknown): value is JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean")
    return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.every(isJson);
  return isRecord(value) && Object.values(value).every(isJson);
}
function isJsonObject(value: unknown): value is JsonObject {
  return isRecord(value) && Object.values(value).every(isJson);
}
function isDecimal(value: unknown): value is string | null {
  return (
    value === null ||
    (typeof value === "string" && /^[+-]?\d+(?:\.\d+)?$/.test(value))
  );
}
function isPositiveCounter(value: unknown): value is number {
  return isCounter(value) && value > 0;
}
export function isJobVersion(value: unknown): value is JobVersion {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    isPositiveCounter(value.version_number) &&
    typeof value.content_hash === "string" &&
    /^[a-f0-9]{64}$/i.test(value.content_hash) &&
    isUuid(value.source_observation_id) &&
    typeof value.title === "string" &&
    [
      "description",
      "location_text",
      "city",
      "region",
      "country_code",
      "workplace_type",
      "employment_type",
      "salary_currency",
      "salary_period",
    ].every((key) => isNullableString(value[key])) &&
    isDecimal(value.salary_min) &&
    isDecimal(value.salary_max) &&
    typeof value.source_url === "string" &&
    isNullableTimestamp(value.source_published_at) &&
    isNullableTimestamp(value.source_updated_at) &&
    isJsonObject(value.canonical_metadata) &&
    isTimestamp(value.effective_from) &&
    isNullableTimestamp(value.effective_to) &&
    typeof value.is_current === "boolean" &&
    isTimestamp(value.created_at)
  );
}
function isJobDetail(value: unknown): value is JobDetailRead {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    isUuid(value.company_id) &&
    isUuid(value.source_connection_id) &&
    typeof value.external_job_id === "string" &&
    isStatus(value.lifecycle_status) &&
    isTimestamp(value.first_seen_at) &&
    isTimestamp(value.last_seen_at) &&
    isNullableTimestamp(value.absence_first_detected_at) &&
    isNullableTimestamp(value.no_longer_observed_at) &&
    isNullableTimestamp(value.reappeared_at) &&
    isCounter(value.consecutive_absent_runs) &&
    isTimestamp(value.created_at) &&
    isTimestamp(value.updated_at) &&
    isJobVersion(value.current_version) &&
    value.current_version.is_current
  );
}
function isJobChange(value: unknown): value is JobChangeEvent {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    typeof value.field_name === "string" &&
    (value.change_type === "added" ||
      value.change_type === "removed" ||
      value.change_type === "modified") &&
    isJson(value.old_value) &&
    isJson(value.new_value) &&
    isUuid(value.from_version_id) &&
    isUuid(value.to_version_id) &&
    isPositiveCounter(value.from_version_number) &&
    isPositiveCounter(value.to_version_number) &&
    isTimestamp(value.detected_at) &&
    isTimestamp(value.created_at)
  );
}
function isLifecycleEvent(value: unknown): value is JobLifecycleEvent {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    isUuid(value.pipeline_run_id) &&
    (value.event_type === "absence_detected" ||
      value.event_type === "not_observed_confirmed" ||
      value.event_type === "reappeared") &&
    isTimestamp(value.occurred_at) &&
    (value.previous_status === null || isStatus(value.previous_status)) &&
    (value.new_status === null || isStatus(value.new_status)) &&
    isJsonObject(value.metadata) &&
    isTimestamp(value.created_at)
  );
}
function guardJobId(jobId: string) {
  if (!isUuid(jobId)) throw new ApiError(0, "INVALID_JOB_ID");
}
export async function getJob(
  jobId: string,
  client = new ApiClient(),
): Promise<JobDetailRead> {
  guardJobId(jobId);
  const { status, body } = await client.getJson(`/api/v1/jobs/${jobId}`);
  if (
    status !== 200 ||
    !isJobDetail(body) ||
    body.id.toLowerCase() !== jobId.toLowerCase()
  )
    throw new ApiError(status, "INVALID_RESPONSE");
  return body;
}
async function readHistory<T>(
  jobId: string,
  endpoint: "versions" | "changes",
  page: number,
  validator: (value: unknown) => value is T,
  client: ApiClient,
): Promise<HistoryPage<T>> {
  guardJobId(jobId);
  const offset = (parseHistoryPage(String(page)) - 1) * HISTORY_PAGE_SIZE;
  const { status, body } = await client.getJson(
    `/api/v1/jobs/${jobId}/${endpoint}?limit=${HISTORY_READ_LIMIT}&offset=${offset}`,
  );
  if (
    status !== 200 ||
    !isRecord(body) ||
    body.limit !== HISTORY_READ_LIMIT ||
    body.offset !== offset ||
    !Array.isArray(body.items) ||
    body.items.length > HISTORY_READ_LIMIT ||
    !body.items.every(validator)
  )
    throw new ApiError(status, "INVALID_RESPONSE");
  if (
    endpoint === "versions" &&
    body.items.filter((item) => isJobVersion(item) && item.is_current).length >
      1
  )
    throw new ApiError(status, "INVALID_RESPONSE");
  return {
    items: body.items.slice(0, HISTORY_PAGE_SIZE),
    hasNext: body.items.length > HISTORY_PAGE_SIZE,
  };
}
export async function getJobVersions(
  jobId: string,
  page = 1,
  client = new ApiClient(),
): Promise<HistoryPage<JobVersion>> {
  const result = await readHistory(
    jobId,
    "versions",
    page,
    isJobVersion,
    client,
  );
  return result;
}
export function getJobChanges(
  jobId: string,
  page = 1,
  client = new ApiClient(),
): Promise<HistoryPage<JobChangeEvent>> {
  return readHistory(jobId, "changes", page, isJobChange, client);
}
export async function getJobLifecycle(
  jobId: string,
  page = 1,
  client = new ApiClient(),
): Promise<{ summary: JobLifecycleRead; hasNext: boolean }> {
  guardJobId(jobId);
  const offset = (parseHistoryPage(String(page)) - 1) * HISTORY_PAGE_SIZE;
  const { status, body } = await client.getJson(
    `/api/v1/jobs/${jobId}/lifecycle?limit=${HISTORY_READ_LIMIT}&offset=${offset}`,
  );
  if (
    status !== 200 ||
    !isRecord(body) ||
    !isUuid(body.job_id) ||
    body.job_id.toLowerCase() !== jobId.toLowerCase() ||
    !isStatus(body.current_status) ||
    !isTimestamp(body.first_seen_at) ||
    !isTimestamp(body.last_seen_at) ||
    !isNullableTimestamp(body.absence_first_detected_at) ||
    !isNullableTimestamp(body.no_longer_observed_at) ||
    !isNullableTimestamp(body.reappeared_at) ||
    !isCounter(body.consecutive_absent_runs) ||
    body.limit !== HISTORY_READ_LIMIT ||
    body.offset !== offset ||
    !Array.isArray(body.events) ||
    body.events.length > HISTORY_READ_LIMIT ||
    !body.events.every(isLifecycleEvent)
  )
    throw new ApiError(status, "INVALID_RESPONSE");
  const summary: JobLifecycleRead = {
    job_id: body.job_id,
    current_status: body.current_status,
    first_seen_at: body.first_seen_at,
    last_seen_at: body.last_seen_at,
    absence_first_detected_at: body.absence_first_detected_at,
    no_longer_observed_at: body.no_longer_observed_at,
    reappeared_at: body.reappeared_at,
    consecutive_absent_runs: body.consecutive_absent_runs,
    events: body.events.slice(0, HISTORY_PAGE_SIZE),
    limit: body.limit,
    offset: body.offset,
  };
  return { summary, hasNext: body.events.length > HISTORY_PAGE_SIZE };
}
