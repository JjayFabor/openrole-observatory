export const HISTORY_PAGE_SIZE = 25;
export const HISTORY_READ_LIMIT = HISTORY_PAGE_SIZE + 1;
export const MAX_HISTORY_PAGE = Math.floor(2147483647 / HISTORY_PAGE_SIZE) + 1;
export type HistorySearchParams = Record<string, string | string[] | undefined>;
export type JobHistoryQuery = {
  versions: number;
  changes: number;
  lifecycle: number;
};

export function parseHistoryPage(value: string | string[] | undefined): number {
  const number =
    typeof value === "string" && /^\d+$/.test(value) ? Number(value) : 1;
  return Number.isSafeInteger(number) &&
    number >= 1 &&
    number <= MAX_HISTORY_PAGE
    ? number
    : 1;
}
export function parseJobHistoryQuery(
  params: HistorySearchParams,
): JobHistoryQuery {
  return {
    versions: parseHistoryPage(params.versions),
    changes: parseHistoryPage(params.changes),
    lifecycle: parseHistoryPage(params.lifecycle),
  };
}
export function buildJobHistoryHref(
  jobId: string,
  state: JobHistoryQuery,
  section: keyof JobHistoryQuery,
  page: number,
): string {
  const next = { ...state, [section]: page };
  const params = new URLSearchParams();
  for (const key of ["versions", "changes", "lifecycle"] as const) {
    const safe = parseHistoryPage(String(next[key]));
    if (safe !== 1) params.set(key, String(safe));
  }
  return `/dashboard/jobs/${jobId}${params.size ? `?${params}` : ""}#${section}`;
}
