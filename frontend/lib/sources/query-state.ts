export const SOURCES_PAGE_SIZE = 25;
export const MAX_SOURCES_PAGE = Math.floor(2147483647 / SOURCES_PAGE_SIZE) + 1;
export type SourcesSearchParams = Record<string, string | string[] | undefined>;
export type SourcesQueryState = { page: number; active?: boolean };

export function parseSourcesQuery(
  params: SourcesSearchParams,
): SourcesQueryState {
  const value = typeof params.page === "string" ? params.page : "";
  const candidate = /^\d+$/.test(value) ? Number(value) : 1;
  const page =
    Number.isSafeInteger(candidate) &&
    candidate >= 1 &&
    candidate <= MAX_SOURCES_PAGE
      ? candidate
      : 1;
  const active =
    params.active === "true"
      ? true
      : params.active === "false"
        ? false
        : undefined;
  return { page, active };
}

export function buildSourcesHref(
  state: SourcesQueryState,
  changes: Partial<SourcesQueryState> = {},
): string {
  const merged = { ...state, ...changes };
  const safe = parseSourcesQuery({
    page: String(merged.page),
    active: merged.active === undefined ? undefined : String(merged.active),
  });
  const params = new URLSearchParams();
  if (safe.active !== undefined) params.set("active", String(safe.active));
  if (safe.page !== 1) params.set("page", String(safe.page));
  const query = params.toString();
  return `/dashboard/sources${query ? `?${query}` : ""}`;
}

export function getSourcesEmptyState(
  total: number,
  state: SourcesQueryState,
): "page" | "filtered" | "unconfigured" {
  if (total > 0) return "page";
  return state.active === undefined ? "unconfigured" : "filtered";
}
