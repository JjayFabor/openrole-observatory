import type { SourceSyncErrorReason, SourceSyncOutcome } from "../api/types";

const errors: Record<SourceSyncErrorReason, string> = {
  not_found:
    "This source no longer exists. Return to Sources to inspect the current configuration.",
  inactive: "This source is inactive and cannot be synchronized.",
  already_running:
    "A synchronization is already running for this source. Refresh to inspect its latest state before trying again.",
  source_timeout:
    "The source request timed out. The synchronization did not complete successfully.",
  source_request_failed:
    "The source request failed. Inspect the latest persisted run for available details.",
  source_response_invalid:
    "The source returned an invalid response. The synchronization did not complete successfully.",
  raw_storage_failed:
    "Raw snapshot storage failed. The synchronization did not complete successfully.",
  database_write_failed:
    "Saving synchronization results failed. Inspect the persisted source state before trying again.",
  pipeline_internal_error:
    "The pipeline could not complete synchronization. Inspect the latest persisted run for available details.",
  timeout_unknown:
    "The synchronization response timed out. Its result is unknown and it may still be running. Refresh the page before trying again.",
  backend_unavailable:
    "The backend could not be reached. The synchronization result is unknown. Refresh the page before trying again.",
  invalid_source:
    "The source identifier is invalid. Return to Sources and open an existing source before trying again.",
  invalid_configuration:
    "The backend connection is not configured correctly. Check the server-side API configuration before trying again.",
  invalid_response:
    "The synchronization response could not be verified. Inspect the persisted source state before trying again.",
  request_failed:
    "The synchronization request could not be completed. Inspect the source state before trying again.",
};

const knownErrors: readonly [number, string, SourceSyncErrorReason][] = [
  [404, "SOURCE_CONNECTION_NOT_FOUND", "not_found"],
  [409, "SOURCE_CONNECTION_INACTIVE", "inactive"],
  [409, "SOURCE_SYNC_ALREADY_RUNNING", "already_running"],
  [504, "SOURCE_REQUEST_TIMEOUT", "source_timeout"],
  [502, "SOURCE_REQUEST_FAILED", "source_request_failed"],
  [502, "SOURCE_RESPONSE_INVALID", "source_response_invalid"],
  [503, "RAW_STORAGE_FAILED", "raw_storage_failed"],
  [500, "DATABASE_WRITE_FAILED", "database_write_failed"],
  [500, "PIPELINE_INTERNAL_ERROR", "pipeline_internal_error"],
];

export function getSourceSyncErrorOutcome(
  status: number,
  code?: string,
): SourceSyncOutcome {
  const known = knownErrors.find(
    ([expectedStatus, expectedCode]) =>
      status === expectedStatus && code === expectedCode,
  );
  const reason =
    known?.[2] ??
    (status === 0 && code === "INVALID_SOURCE_ID"
      ? "invalid_source"
      : status === 0 && code === "INVALID_CONFIGURATION"
        ? "invalid_configuration"
        : status === 0 && code === "TIMEOUT"
          ? "timeout_unknown"
          : status === 0
            ? "backend_unavailable"
            : code === "INVALID_RESPONSE"
              ? "invalid_response"
              : "request_failed");
  return { state: "error", reason, refresh: status > 0 };
}

export function getSourceSyncPresentation(outcome: SourceSyncOutcome): {
  title: string;
  message: string;
  className: string;
} {
  if (outcome.state === "error")
    return {
      title: "Synchronization unsuccessful",
      message: errors[outcome.reason],
      className: "border-red-200 bg-red-50 text-red-900",
    };
  const result = outcome.result;
  if (result.status === "failed")
    return {
      title: "Synchronization failed",
      message:
        "The pipeline reported a failed run. Inspect the persisted run and source state for available details.",
      className: "border-red-200 bg-red-50 text-red-900",
    };
  return {
    title:
      result.status === "completed_with_errors"
        ? "Completed with errors"
        : "Synchronization completed",
    message: `Fetched ${result.records_fetched.toLocaleString("en-US")} records · New ${result.jobs_new.toLocaleString("en-US")} · Changed ${result.jobs_changed.toLocaleString("en-US")} · Unchanged ${result.jobs_unchanged.toLocaleString("en-US")}${result.status === "completed_with_errors" ? ` · Quarantined ${result.records_quarantined.toLocaleString("en-US")}` : ""}.`,
    className:
      result.status === "completed_with_errors"
        ? "border-amber-200 bg-amber-50 text-amber-950"
        : "border-border bg-accent text-accent-foreground",
  };
}
