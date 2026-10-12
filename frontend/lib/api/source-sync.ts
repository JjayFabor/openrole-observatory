import "server-only";
import { ApiClient, ApiError } from "./client";
import type { SourceSyncLifecycle, SourceSyncResponse } from "./types";
import { isCounter, isRecord, isTimestamp, isUuid } from "./validation";

function readLifecycle(value: unknown): SourceSyncLifecycle | null | undefined {
  if (value === undefined || value === null) return value;
  if (
    !isRecord(value) ||
    typeof value.performed !== "boolean" ||
    (value.skipped_reason !== null &&
      value.skipped_reason !== "unidentified_quarantine_records") ||
    ![
      "tentative_absences_reset",
      "jobs_reappeared",
      "first_absences_detected",
      "jobs_confirmed_not_observed",
    ].every((key) => isCounter(value[key]))
  )
    throw new ApiError(200, "INVALID_RESPONSE");
  return {
    performed: value.performed,
    skipped_reason: value.skipped_reason,
    tentative_absences_reset: value.tentative_absences_reset as number,
    jobs_reappeared: value.jobs_reappeared as number,
    first_absences_detected: value.first_absences_detected as number,
    jobs_confirmed_not_observed: value.jobs_confirmed_not_observed as number,
  };
}

export async function syncSource(
  sourceId: string,
  client = new ApiClient(),
): Promise<SourceSyncResponse> {
  if (!isUuid(sourceId)) throw new ApiError(0, "INVALID_SOURCE_ID");
  const { status, body } = await client.postJson(
    `/api/v1/sources/${sourceId}/sync`,
  );
  if (
    status !== 200 ||
    !isRecord(body) ||
    !isUuid(body.pipeline_run_id) ||
    !isUuid(body.source_connection_id) ||
    body.source_connection_id.toLowerCase() !== sourceId.toLowerCase() ||
    (body.status !== "completed" &&
      body.status !== "completed_with_errors" &&
      body.status !== "failed") ||
    !isTimestamp(body.started_at) ||
    !isTimestamp(body.completed_at) ||
    Date.parse(body.completed_at) < Date.parse(body.started_at) ||
    ![
      "records_fetched",
      "records_valid",
      "records_quarantined",
      "jobs_new",
      "jobs_changed",
      "jobs_unchanged",
    ].every((key) => isCounter(body[key]))
  )
    throw new ApiError(status, "INVALID_RESPONSE");
  const lifecycle = readLifecycle(body.lifecycle);
  return {
    pipeline_run_id: body.pipeline_run_id,
    source_connection_id: body.source_connection_id,
    status: body.status,
    records_fetched: body.records_fetched as number,
    records_valid: body.records_valid as number,
    records_quarantined: body.records_quarantined as number,
    jobs_new: body.jobs_new as number,
    jobs_changed: body.jobs_changed as number,
    jobs_unchanged: body.jobs_unchanged as number,
    started_at: body.started_at,
    completed_at: body.completed_at,
    ...(lifecycle === undefined ? {} : { lifecycle }),
  };
}
