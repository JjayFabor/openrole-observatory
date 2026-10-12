import type { PipelineRun, SourceHealth } from "../lib/api/types";

export const sourceId = "11111111-1111-4111-8111-111111111111";

export function pipelineRun(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    source_connection_id: sourceId,
    status: "completed",
    started_at: "2026-10-09T10:00:00Z",
    completed_at: "2026-10-09T10:01:18Z",
    records_fetched: 10,
    records_valid: 8,
    records_quarantined: 2,
    jobs_new: 3,
    jobs_changed: 1,
    jobs_unchanged: 4,
    error_code: null,
    error_summary: null,
    created_at: "2026-10-09T10:00:00Z",
    ...overrides,
  };
}

export function sourceHealth(
  overrides: Partial<SourceHealth> = {},
): SourceHealth {
  return {
    id: sourceId,
    company_id: "33333333-3333-4333-8333-333333333333",
    provider: "greenhouse",
    is_active: true,
    last_attempted_sync_at: "2026-10-09T10:00:00Z",
    last_successful_sync_at: "2026-10-09T10:01:18Z",
    latest_run: pipelineRun(),
    ...overrides,
  };
}
