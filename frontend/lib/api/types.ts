export type SourceProvider = "greenhouse";
export type HealthResponse = { status: "ok" };

export type ReadinessResponse =
  | { status: "ready"; database: "available" }
  | { status: "not_ready"; database: "unavailable" };

export type SystemStatus = {
  api: "healthy" | "unavailable";
  database: "ready" | "not_ready" | "unavailable";
};

export const pipelineStatuses = [
  "pending",
  "running",
  "completed",
  "completed_with_errors",
  "failed",
] as const;
export type PipelineStatus = (typeof pipelineStatuses)[number];

export type PipelineRun = {
  id: string;
  source_connection_id: string;
  status: PipelineStatus;
  started_at: string;
  completed_at: string | null;
  records_fetched: number;
  records_valid: number;
  records_quarantined: number;
  jobs_new: number;
  jobs_changed: number;
  jobs_unchanged: number;
  error_code: string | null;
  error_summary: string | null;
  created_at: string;
};

export type PipelineRunListResponse = {
  items: PipelineRun[];
  limit: number;
  offset: number;
};

export type SourceHealth = {
  id: string;
  company_id: string;
  provider: SourceProvider;
  is_active: boolean;
  last_attempted_sync_at: string | null;
  last_successful_sync_at: string | null;
  latest_run: PipelineRun | null;
};

export type SourceSection =
  | { state: "available"; source: SourceHealth }
  | { state: "unconfigured" }
  | {
      state: "unavailable";
      reason: "not_found" | "invalid_configuration" | "request_failed";
    };

export type RunsSection =
  | { state: "available"; runs: PipelineRun[] }
  | { state: "unavailable" };

export type OverviewData = {
  system: SystemStatus;
  source: SourceSection;
  runs: RunsSection;
  fetchedAt: number;
};

export type JobLifecycleStatus = "observed" | "not_observed";

export type JobListItem = {
  id: string;
  external_job_id: string;
  company: { id: string; name: string };
  source: { id: string; provider: SourceProvider };
  lifecycle_status: JobLifecycleStatus;
  first_seen_at: string;
  last_seen_at: string;
  absence_first_detected_at: string | null;
  reappeared_at: string | null;
  consecutive_absent_runs: number;
  current_version: {
    id: string;
    version_number: number;
    title: string;
    location_text: string | null;
    workplace_type: string | null;
    employment_type: string | null;
  };
};

export type JobListResponse = {
  items: JobListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };
export type QuarantineStatus = "open" | "resolved";

export type QuarantineListItem = {
  id: string;
  pipeline_run_id: string;
  source_connection_id: string;
  raw_snapshot_id: string;
  external_job_id: string | null;
  raw_record_locator: string | null;
  error_category: string;
  error_code: string | null;
  error_message: string;
  status: QuarantineStatus;
  created_at: string;
  resolved_at: string | null;
  source: { provider: SourceProvider; company_name: string };
};

export type QuarantineRecordDetail = QuarantineListItem & {
  error_details: JsonObject;
};
export type PaginatedQuarantineRecords = {
  items: QuarantineListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type SourceCompany = {
  id: string;
  name: string;
  domain: string | null;
  careers_url: string | null;
};
export type SourceRead = SourceHealth & { company: SourceCompany };
export type SourceListResponse = {
  items: SourceRead[];
  total: number;
  limit: number;
  offset: number;
};
export type SourceQuarantineSection =
  | { state: "available"; records: QuarantineListItem[] }
  | { state: "unavailable" };
export type SourceDetailResult =
  | {
      state: "available";
      source: SourceRead;
      runs: RunsSection;
      quarantine: SourceQuarantineSection;
      fetchedAt: number;
    }
  | { state: "not_found" | "unavailable" };

export type SourceSyncLifecycle = {
  performed: boolean;
  skipped_reason: "unidentified_quarantine_records" | null;
  tentative_absences_reset: number;
  jobs_reappeared: number;
  first_absences_detected: number;
  jobs_confirmed_not_observed: number;
};

export type SourceSyncResponse = {
  pipeline_run_id: string;
  source_connection_id: string;
  status: "completed" | "completed_with_errors" | "failed";
  records_fetched: number;
  records_valid: number;
  records_quarantined: number;
  jobs_new: number;
  jobs_changed: number;
  jobs_unchanged: number;
  started_at: string;
  completed_at: string;
  lifecycle?: SourceSyncLifecycle | null;
};

export type SourceSyncErrorReason =
  | "not_found"
  | "inactive"
  | "already_running"
  | "source_timeout"
  | "source_request_failed"
  | "source_response_invalid"
  | "raw_storage_failed"
  | "database_write_failed"
  | "pipeline_internal_error"
  | "timeout_unknown"
  | "backend_unavailable"
  | "invalid_source"
  | "invalid_configuration"
  | "invalid_response"
  | "request_failed";

export type SourceSyncOutcome =
  | { state: "result"; result: SourceSyncResponse }
  | { state: "error"; reason: SourceSyncErrorReason; refresh: boolean };

export type JobVersion = {
  id: string;
  version_number: number;
  content_hash: string;
  source_observation_id: string;
  title: string;
  description: string | null;
  location_text: string | null;
  city: string | null;
  region: string | null;
  country_code: string | null;
  workplace_type: string | null;
  employment_type: string | null;
  salary_min: string | null;
  salary_max: string | null;
  salary_currency: string | null;
  salary_period: string | null;
  source_url: string;
  source_published_at: string | null;
  source_updated_at: string | null;
  canonical_metadata: JsonObject;
  effective_from: string;
  effective_to: string | null;
  is_current: boolean;
  created_at: string;
};
export type JobDetailRead = {
  id: string;
  company_id: string;
  source_connection_id: string;
  external_job_id: string;
  lifecycle_status: JobLifecycleStatus;
  first_seen_at: string;
  last_seen_at: string;
  absence_first_detected_at: string | null;
  no_longer_observed_at: string | null;
  reappeared_at: string | null;
  consecutive_absent_runs: number;
  created_at: string;
  updated_at: string;
  current_version: JobVersion;
};
export type JobChangeEvent = {
  id: string;
  field_name: string;
  change_type: "added" | "removed" | "modified";
  old_value: JsonValue;
  new_value: JsonValue;
  from_version_id: string;
  to_version_id: string;
  from_version_number: number;
  to_version_number: number;
  detected_at: string;
  created_at: string;
};
export type JobLifecycleEvent = {
  id: string;
  pipeline_run_id: string;
  event_type: "absence_detected" | "not_observed_confirmed" | "reappeared";
  occurred_at: string;
  previous_status: JobLifecycleStatus | null;
  new_status: JobLifecycleStatus | null;
  metadata: JsonObject;
  created_at: string;
};
export type JobLifecycleRead = {
  job_id: string;
  current_status: JobLifecycleStatus;
  first_seen_at: string;
  last_seen_at: string;
  absence_first_detected_at: string | null;
  no_longer_observed_at: string | null;
  reappeared_at: string | null;
  consecutive_absent_runs: number;
  events: JobLifecycleEvent[];
  limit: number;
  offset: number;
};
export type HistoryPage<T> = { items: T[]; hasNext: boolean };
export type InspectionSection<T> =
  | { state: "available"; data: T }
  | { state: "unavailable" };
export type JobDetailResult =
  | {
      state: "available";
      job: JobDetailRead;
      source: InspectionSection<SourceRead>;
      versions: InspectionSection<HistoryPage<JobVersion>>;
      changes: InspectionSection<HistoryPage<JobChangeEvent>>;
      lifecycle: InspectionSection<{
        summary: JobLifecycleRead;
        hasNext: boolean;
      }>;
    }
  | { state: "not_found" | "unavailable" };
export type RunDetailResult =
  | {
      state: "available";
      run: PipelineRun;
      source: InspectionSection<SourceRead>;
    }
  | { state: "not_found" | "unavailable" };
