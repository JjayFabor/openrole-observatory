import "server-only";
import { ApiClient, ApiError } from "./client";
import type {
  JsonObject,
  JsonValue,
  PaginatedQuarantineRecords,
  QuarantineListItem,
  QuarantineRecordDetail,
} from "./types";
import {
  isCounter,
  isNullableTimestamp,
  isRecord,
  isTimestamp,
  isUuid,
} from "./validation";
import {
  parseQuarantineQuery,
  QUARANTINE_PAGE_SIZE,
  type QuarantineQueryState,
} from "../quarantine/query-state";

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isQuarantineListItem(value: unknown): value is QuarantineListItem {
  if (!isRecord(value) || !isRecord(value.source)) return false;
  return (
    isUuid(value.id) &&
    isUuid(value.pipeline_run_id) &&
    isUuid(value.source_connection_id) &&
    isUuid(value.raw_snapshot_id) &&
    isNullableString(value.external_job_id) &&
    isNullableString(value.raw_record_locator) &&
    typeof value.error_category === "string" &&
    isNullableString(value.error_code) &&
    typeof value.error_message === "string" &&
    (value.status === "open" || value.status === "resolved") &&
    isTimestamp(value.created_at) &&
    isNullableTimestamp(value.resolved_at) &&
    value.source.provider === "greenhouse" &&
    typeof value.source.company_name === "string"
  );
}

function isJsonValue(value: unknown): value is JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean")
    return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.every(isJsonValue);
  return isRecord(value) && Object.values(value).every(isJsonValue);
}

function isJsonObject(value: unknown): value is JsonObject {
  return isRecord(value) && Object.values(value).every(isJsonValue);
}

export async function listQuarantineRecords(
  state: QuarantineQueryState,
  client = new ApiClient(),
  limit = QUARANTINE_PAGE_SIZE,
): Promise<PaginatedQuarantineRecords> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100)
    throw new ApiError(0, "INVALID_LIMIT");
  const query = parseQuarantineQuery({ ...state, page: String(state.page) });
  const maxPage = Math.floor(2147483647 / limit) + 1;
  const page = query.page <= maxPage ? query.page : 1;
  const offset = (page - 1) * limit;
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (query.status) params.set("status", query.status);
  if (query.source) params.set("source_connection_id", query.source);
  if (query.run) params.set("pipeline_run_id", query.run);
  if (query.category) params.set("error_category", query.category);
  const { status, body } = await client.getJson(`/api/v1/quarantine?${params}`);
  if (
    status !== 200 ||
    !isRecord(body) ||
    body.limit !== limit ||
    body.offset !== offset ||
    !isCounter(body.total) ||
    !Array.isArray(body.items) ||
    body.items.length > limit ||
    body.items.length > body.total ||
    !body.items.every(isQuarantineListItem) ||
    (query.source !== undefined &&
      body.items.some(
        (record) =>
          record.source_connection_id.toLowerCase() !==
          query.source!.toLowerCase(),
      ))
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

export async function getQuarantineRecord(
  recordId: string,
  client = new ApiClient(),
): Promise<QuarantineRecordDetail> {
  if (!isUuid(recordId)) throw new ApiError(0, "INVALID_RECORD_ID");
  const { status, body } = await client.getJson(
    `/api/v1/quarantine/${recordId}`,
  );
  if (!isRecord(body)) throw new ApiError(status, "INVALID_RESPONSE");
  const details = body.error_details;
  if (
    status !== 200 ||
    !isQuarantineListItem(body) ||
    body.id.toLowerCase() !== recordId.toLowerCase() ||
    !isJsonObject(details)
  ) {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  return { ...body, error_details: details };
}
