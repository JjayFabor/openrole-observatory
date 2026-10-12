import type {
  JobChangeEvent,
  JobDetailRead,
  JobDetailResult,
  JobLifecycleRead,
  JobVersion,
} from "../lib/api/types";
import { sourceRead } from "./source-fixtures";
export const jobId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export function jobVersion(overrides: Partial<JobVersion> = {}): JobVersion {
  return {
    id: "44444444-4444-4444-8444-444444444444",
    version_number: 2,
    content_hash: "a".repeat(64),
    source_observation_id: "55555555-5555-4555-8555-555555555555",
    title: "Backend Engineer",
    description: "<p>Build reliable pipelines.</p>",
    location_text: "Remote",
    city: null,
    region: null,
    country_code: null,
    workplace_type: "remote",
    employment_type: "full_time",
    salary_min: "90000.00",
    salary_max: "120000.00",
    salary_currency: "USD",
    salary_period: "year",
    source_url: "https://example.test/jobs/123",
    source_published_at: null,
    source_updated_at: null,
    canonical_metadata: { zero: 0, enabled: false, nested: { value: null } },
    effective_from: "2026-10-09T10:00:00Z",
    effective_to: null,
    is_current: true,
    created_at: "2026-10-09T10:00:00Z",
    ...overrides,
  };
}
export function jobRead(overrides: Partial<JobDetailRead> = {}): JobDetailRead {
  const source = sourceRead();
  return {
    id: jobId,
    company_id: source.company_id,
    source_connection_id: source.id,
    external_job_id: "1001",
    lifecycle_status: "observed",
    first_seen_at: "2026-10-01T10:00:00Z",
    last_seen_at: "2026-10-09T10:00:00Z",
    absence_first_detected_at: null,
    no_longer_observed_at: "2026-10-08T10:00:00Z",
    reappeared_at: "2026-10-09T10:00:00Z",
    consecutive_absent_runs: 0,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-09T10:00:00Z",
    current_version: jobVersion(),
    ...overrides,
  };
}
export function jobChange(
  overrides: Partial<JobChangeEvent> = {},
): JobChangeEvent {
  return {
    id: "66666666-6666-4666-8666-666666666666",
    field_name: "workplace_type",
    change_type: "modified",
    old_value: "remote",
    new_value: "hybrid",
    from_version_id: "77777777-7777-4777-8777-777777777777",
    to_version_id: jobVersion().id,
    from_version_number: 1,
    to_version_number: 2,
    detected_at: "2026-10-09T10:00:00Z",
    created_at: "2026-10-09T10:00:00Z",
    ...overrides,
  };
}
export function jobLifecycle(
  overrides: Partial<JobLifecycleRead> = {},
): JobLifecycleRead {
  const job = jobRead();
  return {
    job_id: job.id,
    current_status: job.lifecycle_status,
    first_seen_at: job.first_seen_at,
    last_seen_at: job.last_seen_at,
    absence_first_detected_at: job.absence_first_detected_at,
    no_longer_observed_at: job.no_longer_observed_at,
    reappeared_at: job.reappeared_at,
    consecutive_absent_runs: job.consecutive_absent_runs,
    events: [
      {
        id: "88888888-8888-4888-8888-888888888888",
        pipeline_run_id: "22222222-2222-4222-8222-222222222222",
        event_type: "reappeared",
        occurred_at: "2026-10-09T10:00:00Z",
        previous_status: "not_observed",
        new_status: "observed",
        metadata: { consecutive_absent_runs: 0 },
        created_at: "2026-10-09T10:00:00Z",
      },
    ],
    limit: 26,
    offset: 0,
    ...overrides,
  };
}
export function jobDetailFixture(): Extract<
  JobDetailResult,
  { state: "available" }
> {
  return {
    state: "available",
    job: jobRead(),
    source: { state: "available", data: sourceRead() },
    versions: {
      state: "available",
      data: { items: [jobVersion()], hasNext: false },
    },
    changes: {
      state: "available",
      data: { items: [jobChange()], hasNext: false },
    },
    lifecycle: {
      state: "available",
      data: { summary: jobLifecycle(), hasNext: false },
    },
  };
}
