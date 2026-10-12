import type {
  QuarantineListItem,
  QuarantineRecordDetail,
} from "../lib/api/types";

export const quarantineId = "11111111-1111-4111-8111-111111111111";
export const quarantineRunId = "22222222-2222-4222-8222-222222222222";
export const quarantineSourceId = "33333333-3333-4333-8333-333333333333";

export function quarantineRecord(
  overrides: Partial<QuarantineListItem> = {},
): QuarantineListItem {
  return {
    id: quarantineId,
    pipeline_run_id: quarantineRunId,
    source_connection_id: quarantineSourceId,
    raw_snapshot_id: "44444444-4444-4444-8444-444444444444",
    external_job_id: "12345",
    raw_record_locator: "jobs[17]",
    error_category: "record_validation_failed",
    error_code: "MISSING_TITLE",
    error_message: "Title is required.",
    status: "open",
    created_at: "2026-10-09T10:00:00Z",
    resolved_at: null,
    source: { provider: "greenhouse", company_name: "Example Company" },
    ...overrides,
  };
}

export function quarantineDetail(
  overrides: Partial<QuarantineRecordDetail> = {},
): QuarantineRecordDetail {
  return {
    ...quarantineRecord(),
    error_details: {
      field: "title",
      nested: { valid: false, count: 0, value: null },
      values: ["text", 0, false, null],
    },
    ...overrides,
  };
}
