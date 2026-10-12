import "server-only";
import { ApiClient, ApiError } from "./client";
import type {
  PublicJobDetail,
  PublicJobListItem,
  PublicJobListResponse,
} from "./public-jobs-types";
import {
  isCounter,
  isNullableTimestamp,
  isRecord,
  isTimestamp,
  isUuid,
} from "./validation";
import {
  parsePublicJobsQuery,
  PUBLIC_JOBS_PAGE_SIZE,
  type PublicJobsQueryState,
} from "../public-jobs/query-state";

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNullableDecimal(value: unknown): value is string | null {
  return (
    value === null ||
    (typeof value === "string" && /^-?\d+(?:\.\d+)?$/.test(value))
  );
}

function isPublicHttpUrl(value: unknown): value is string {
  if (typeof value !== "string" || !/^https?:\/\//i.test(value)) return false;
  try {
    const url = new URL(value);
    return (
      ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}

function isPublicJobListItem(value: unknown): value is PublicJobListItem {
  if (!isRecord(value) || !isRecord(value.company) || !isRecord(value.source)) {
    return false;
  }
  return (
    isUuid(value.id) &&
    typeof value.title === "string" &&
    typeof value.company.name === "string" &&
    isNullableString(value.company.domain) &&
    value.source.provider === "greenhouse" &&
    [
      "location_text",
      "city",
      "region",
      "country_code",
      "workplace_type",
      "employment_type",
      "salary_currency",
      "salary_period",
    ].every((field) => isNullableString(value[field])) &&
    isNullableDecimal(value.salary_min) &&
    isNullableDecimal(value.salary_max) &&
    isTimestamp(value.first_seen_at) &&
    isTimestamp(value.last_seen_at)
  );
}

function projectPublicJob(item: PublicJobListItem): PublicJobListItem {
  return {
    id: item.id,
    title: item.title,
    company: { name: item.company.name, domain: item.company.domain },
    location_text: item.location_text,
    city: item.city,
    region: item.region,
    country_code: item.country_code,
    workplace_type: item.workplace_type,
    employment_type: item.employment_type,
    salary_min: item.salary_min,
    salary_max: item.salary_max,
    salary_currency: item.salary_currency,
    salary_period: item.salary_period,
    first_seen_at: item.first_seen_at,
    last_seen_at: item.last_seen_at,
    source: { provider: item.source.provider },
  };
}

export async function listPublicJobs(
  state: PublicJobsQueryState,
  client = new ApiClient(),
): Promise<PublicJobListResponse> {
  const query = parsePublicJobsQuery({ ...state, page: String(state.page) });
  const offset = (query.page - 1) * PUBLIC_JOBS_PAGE_SIZE;
  const params = new URLSearchParams({
    limit: String(PUBLIC_JOBS_PAGE_SIZE),
    offset: String(offset),
  });
  if (query.q) params.set("q", query.q);
  if (query.location) params.set("location", query.location);
  if (query.workplace) params.set("workplace_type", query.workplace);
  if (query.employment) params.set("employment_type", query.employment);
  const { status, body } = await client.getJson(
    `/api/v1/public/jobs?${params}`,
  );
  if (
    status !== 200 ||
    !isRecord(body) ||
    body.limit !== PUBLIC_JOBS_PAGE_SIZE ||
    body.offset !== offset ||
    !isCounter(body.total) ||
    !Array.isArray(body.items) ||
    body.items.length > PUBLIC_JOBS_PAGE_SIZE ||
    !body.items.every(isPublicJobListItem)
  ) {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  // Count and page are separate backend reads; a changing dataset can make their sizes differ.
  return {
    items: body.items.map(projectPublicJob),
    total: body.total,
    limit: body.limit,
    offset: body.offset,
  };
}

export async function getPublicJob(
  jobId: string,
  client = new ApiClient(),
): Promise<PublicJobDetail | null> {
  if (!isUuid(jobId)) return null;
  const { status, body } = await client.getJson(
    `/api/v1/public/jobs/${jobId}`,
    [404],
  );
  if (
    status === 404 &&
    isRecord(body) &&
    isRecord(body.error) &&
    body.error.code === "JOB_NOT_FOUND"
  ) {
    return null;
  }
  if (
    status !== 200 ||
    !isPublicJobListItem(body) ||
    body.id.toLowerCase() !== jobId.toLowerCase() ||
    !("careers_url" in body.company) ||
    !(
      body.company.careers_url === null ||
      isPublicHttpUrl(body.company.careers_url)
    ) ||
    !("description" in body) ||
    !isNullableString(body.description) ||
    !("source_url" in body) ||
    !isPublicHttpUrl(body.source_url) ||
    !("lifecycle_status" in body) ||
    !(
      body.lifecycle_status === "observed" ||
      body.lifecycle_status === "not_observed"
    ) ||
    !("absence_first_detected_at" in body) ||
    !isNullableTimestamp(body.absence_first_detected_at) ||
    !("no_longer_observed_at" in body) ||
    !isNullableTimestamp(body.no_longer_observed_at) ||
    !("reappeared_at" in body) ||
    !isNullableTimestamp(body.reappeared_at)
  ) {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  return {
    ...projectPublicJob(body),
    company: {
      name: body.company.name,
      domain: body.company.domain,
      careers_url: body.company.careers_url,
    },
    description: body.description,
    source_url: body.source_url,
    lifecycle_status: body.lifecycle_status,
    absence_first_detected_at: body.absence_first_detected_at,
    no_longer_observed_at: body.no_longer_observed_at,
    reappeared_at: body.reappeared_at,
  };
}
