import "server-only";
import { ApiClient, ApiError } from "./client";
import type { SourceHealth, SourceListResponse, SourceRead } from "./types";
import { isCounter } from "./validation";
import {
  parseSourcesQuery,
  SOURCES_PAGE_SIZE,
  type SourcesQueryState,
} from "../sources/query-state";
import {
  isNullableTimestamp,
  isPipelineRun,
  isRecord,
  isUuid,
} from "./validation";

function isSourceHealth(value: unknown): value is SourceHealth {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    isUuid(value.company_id) &&
    value.provider === "greenhouse" &&
    typeof value.is_active === "boolean" &&
    isNullableTimestamp(value.last_attempted_sync_at) &&
    isNullableTimestamp(value.last_successful_sync_at) &&
    (value.latest_run === null || isPipelineRun(value.latest_run))
  );
}

function isSourceRead(value: unknown): value is SourceRead {
  if (!isRecord(value) || !isRecord(value.company)) return false;
  const company = value.company;
  return (
    isSourceHealth(value) &&
    (value.latest_run === null ||
      value.latest_run.source_connection_id.toLowerCase() ===
        value.id.toLowerCase()) &&
    isUuid(company.id) &&
    company.id === value.company_id &&
    typeof company.name === "string" &&
    (company.domain === null || typeof company.domain === "string") &&
    (company.careers_url === null || typeof company.careers_url === "string")
  );
}

function projectSource(source: SourceRead): SourceRead {
  return {
    id: source.id,
    company_id: source.company_id,
    provider: source.provider,
    is_active: source.is_active,
    last_attempted_sync_at: source.last_attempted_sync_at,
    last_successful_sync_at: source.last_successful_sync_at,
    latest_run: source.latest_run,
    company: {
      id: source.company.id,
      name: source.company.name,
      domain: source.company.domain,
      careers_url: source.company.careers_url,
    },
  };
}

export async function getSourceHealth(
  sourceId: string,
  client = new ApiClient(),
): Promise<SourceHealth> {
  if (!isUuid(sourceId)) throw new ApiError(0, "INVALID_SOURCE_ID");
  const { status, body } = await client.getJson(`/api/v1/sources/${sourceId}`);
  if (
    status !== 200 ||
    !isSourceHealth(body) ||
    body.id.toLowerCase() !== sourceId.toLowerCase() ||
    (body.latest_run !== null &&
      body.latest_run.source_connection_id.toLowerCase() !==
        sourceId.toLowerCase())
  ) {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  return {
    id: body.id,
    company_id: body.company_id,
    provider: body.provider,
    is_active: body.is_active,
    last_attempted_sync_at: body.last_attempted_sync_at,
    last_successful_sync_at: body.last_successful_sync_at,
    latest_run: body.latest_run,
  };
}

export async function listSources(
  state: SourcesQueryState,
  client = new ApiClient(),
): Promise<SourceListResponse> {
  const query = parseSourcesQuery({
    page: String(state.page),
    active: state.active === undefined ? undefined : String(state.active),
  });
  const offset = (query.page - 1) * SOURCES_PAGE_SIZE;
  const params = new URLSearchParams({
    limit: String(SOURCES_PAGE_SIZE),
    offset: String(offset),
  });
  if (query.active !== undefined) params.set("is_active", String(query.active));
  const { status, body } = await client.getJson(`/api/v1/sources?${params}`);
  if (
    status !== 200 ||
    !isRecord(body) ||
    body.limit !== SOURCES_PAGE_SIZE ||
    body.offset !== offset ||
    !isCounter(body.total) ||
    !Array.isArray(body.items) ||
    body.items.length > SOURCES_PAGE_SIZE ||
    body.items.length > body.total ||
    !body.items.every(isSourceRead)
  )
    throw new ApiError(status, "INVALID_RESPONSE");
  return {
    items: body.items.map(projectSource),
    total: body.total,
    limit: body.limit,
    offset: body.offset,
  };
}

export async function getSource(
  sourceId: string,
  client = new ApiClient(),
): Promise<SourceRead> {
  if (!isUuid(sourceId)) throw new ApiError(0, "INVALID_SOURCE_ID");
  const { status, body } = await client.getJson(`/api/v1/sources/${sourceId}`);
  if (
    status !== 200 ||
    !isSourceRead(body) ||
    body.id.toLowerCase() !== sourceId.toLowerCase()
  )
    throw new ApiError(status, "INVALID_RESPONSE");
  return projectSource(body);
}
