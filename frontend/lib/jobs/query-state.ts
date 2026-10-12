import type { JobLifecycleStatus } from "../api/types";
import { isUuid } from "../api/validation";

export const JOBS_PAGE_SIZE = 25;
// PostgreSQL LIMIT/OFFSET values must fit the backend's integer range.
export const MAX_JOBS_PAGE = Math.floor(2147483647 / JOBS_PAGE_SIZE) + 1;

export type JobsSearchParams = Record<string, string | string[] | undefined>;
export type JobsQueryState = {
  page: number;
  status?: JobLifecycleStatus;
  source?: string;
  q?: string;
};

export function parseJobsQuery(params: JobsSearchParams): JobsQueryState {
  const pageValue = typeof params.page === "string" ? params.page : "";
  const candidate = /^\d+$/.test(pageValue) ? Number(pageValue) : 1;
  const page =
    Number.isSafeInteger(candidate) &&
    candidate >= 1 &&
    candidate <= MAX_JOBS_PAGE
      ? candidate
      : 1;
  const status =
    params.status === "observed" || params.status === "not_observed"
      ? params.status
      : undefined;
  const source =
    typeof params.source === "string" && isUuid(params.source)
      ? params.source
      : undefined;
  const text = typeof params.q === "string" ? params.q.trim() : "";
  const q = Array.from(text).slice(0, 200).join("") || undefined;
  return { page, status, source, q };
}

export function buildJobsHref(
  state: JobsQueryState,
  changes: Partial<JobsQueryState> = {},
): string {
  const merged = { ...state, ...changes };
  const safe = parseJobsQuery({
    page: String(merged.page),
    status: merged.status,
    source: merged.source,
    q: merged.q,
  });
  const params = new URLSearchParams();
  if (safe.status) params.set("status", safe.status);
  if (safe.source) params.set("source", safe.source);
  if (safe.q) params.set("q", safe.q);
  if (safe.page !== 1) params.set("page", String(safe.page));
  const query = params.toString();
  return `/dashboard/jobs${query ? `?${query}` : ""}`;
}

export function hasJobsFilters(state: JobsQueryState): boolean {
  return Boolean(state.status || state.source || state.q);
}

export function getJobsEmptyState(
  total: number,
  state: JobsQueryState,
): "page" | "filtered" | "unobserved" {
  if (total > 0) return "page";
  return hasJobsFilters(state) ? "filtered" : "unobserved";
}
