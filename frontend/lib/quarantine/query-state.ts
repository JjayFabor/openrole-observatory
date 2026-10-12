import type { QuarantineStatus } from "../api/types";
import { isUuid } from "../api/validation";

export const QUARANTINE_PAGE_SIZE = 25;
export const MAX_QUARANTINE_PAGE =
  Math.floor(2147483647 / QUARANTINE_PAGE_SIZE) + 1;
export type QuarantineSearchParams = Record<
  string,
  string | string[] | undefined
>;
export type QuarantineQueryState = {
  page: number;
  status?: QuarantineStatus;
  source?: string;
  run?: string;
  category?: string;
};

export function parseQuarantineQuery(
  params: QuarantineSearchParams,
): QuarantineQueryState {
  const value = typeof params.page === "string" ? params.page : "";
  const candidate = /^\d+$/.test(value) ? Number(value) : 1;
  const page =
    Number.isSafeInteger(candidate) &&
    candidate >= 1 &&
    candidate <= MAX_QUARANTINE_PAGE
      ? candidate
      : 1;
  const status =
    params.status === "open" || params.status === "resolved"
      ? params.status
      : undefined;
  const source = isUuid(params.source) ? params.source : undefined;
  const run = isUuid(params.run) ? params.run : undefined;
  const category =
    typeof params.category === "string"
      ? Array.from(params.category.trim()).slice(0, 100).join("") || undefined
      : undefined;
  return { page, status, source, run, category };
}

export function buildQuarantineHref(
  state: QuarantineQueryState,
  changes: Partial<QuarantineQueryState> = {},
): string {
  const merged = { ...state, ...changes };
  const safe = parseQuarantineQuery({ ...merged, page: String(merged.page) });
  const params = new URLSearchParams();
  if (safe.status) params.set("status", safe.status);
  if (safe.source) params.set("source", safe.source);
  if (safe.run) params.set("run", safe.run);
  if (safe.category) params.set("category", safe.category);
  if (safe.page !== 1) params.set("page", String(safe.page));
  const query = params.toString();
  return `/dashboard/quarantine${query ? `?${query}` : ""}`;
}

export function hasQuarantineFilters(state: QuarantineQueryState): boolean {
  return Boolean(state.status || state.source || state.run || state.category);
}

export function getQuarantineEmptyState(
  total: number,
  state: QuarantineQueryState,
): "page" | "filtered" | "unfiltered" {
  if (total > 0) return "page";
  return hasQuarantineFilters(state) ? "filtered" : "unfiltered";
}
