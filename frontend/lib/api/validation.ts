import type { PipelineRun } from "./types";
import { pipelineStatuses } from "./types";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isUuid(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}

export function isTimestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value,
    ) &&
    Number.isFinite(Date.parse(value))
  );
}

export function isNullableTimestamp(value: unknown): value is string | null {
  return value === null || isTimestamp(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

export function isCounter(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

export function isPipelineRun(value: unknown): value is PipelineRun {
  if (!isRecord(value)) return false;
  return (
    isUuid(value.id) &&
    isUuid(value.source_connection_id) &&
    pipelineStatuses.some((status) => value.status === status) &&
    isTimestamp(value.started_at) &&
    isNullableTimestamp(value.completed_at) &&
    isTimestamp(value.created_at) &&
    isNullableString(value.error_code) &&
    isNullableString(value.error_summary) &&
    [
      "records_fetched",
      "records_valid",
      "records_quarantined",
      "jobs_new",
      "jobs_changed",
      "jobs_unchanged",
    ].every((key) => isCounter(value[key]))
  );
}
