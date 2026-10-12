import { pipelineStatuses, type PipelineStatus } from "../api/types";
import { isUuid } from "../api/validation";
import { parseHistoryPage } from "../jobs/history-query";
export const RUNS_PAGE_SIZE = 25;
export const RUNS_READ_LIMIT = 26;
export type RunsQueryState = {
  page: number;
  status?: PipelineStatus;
  source?: string;
};
export type RunsSearchParams = Record<string, string | string[] | undefined>;
export function parseRunsQuery(params: RunsSearchParams): RunsQueryState {
  const status = pipelineStatuses.find((value) => value === params.status);
  return {
    page: parseHistoryPage(params.page),
    status,
    source: isUuid(params.source) ? params.source : undefined,
  };
}
export function buildRunsHref(
  state: RunsQueryState,
  changes: Partial<RunsQueryState> = {},
): string {
  const next = { ...state, ...changes };
  const safe = parseRunsQuery({
    page: String(next.page),
    status: next.status,
    source: next.source,
  });
  const params = new URLSearchParams();
  if (safe.status) params.set("status", safe.status);
  if (safe.source) params.set("source", safe.source);
  if (safe.page !== 1) params.set("page", String(safe.page));
  return `/dashboard/runs${params.size ? `?${params}` : ""}`;
}
