import type {
  PublicEmploymentFilter,
  PublicWorkplaceFilter,
} from "../api/public-jobs-types";

export const PUBLIC_JOBS_PAGE_SIZE = 25;
export const MAX_PUBLIC_JOBS_PAGE =
  Math.floor(2147483647 / PUBLIC_JOBS_PAGE_SIZE) + 1;

export const publicWorkplaceOptions = [
  "remote",
  "hybrid",
  "onsite",
] as const satisfies readonly PublicWorkplaceFilter[];
export const publicEmploymentOptions = [
  "full_time",
  "part_time",
  "contract",
  "temporary",
  "internship",
  "volunteer",
  "other",
] as const satisfies readonly PublicEmploymentFilter[];

export type PublicJobsSearchParams = Record<
  string,
  string | string[] | undefined
>;
export type PublicJobsQueryState = {
  page: number;
  q?: string;
  location?: string;
  workplace?: PublicWorkplaceFilter;
  employment?: PublicEmploymentFilter;
};

function normalizedText(value: string | string[] | undefined) {
  if (typeof value !== "string") return undefined;
  return Array.from(value.trim()).slice(0, 200).join("") || undefined;
}

export function parsePublicJobsQuery(
  params: PublicJobsSearchParams,
): PublicJobsQueryState {
  const rawPage = typeof params.page === "string" ? params.page : "";
  const candidate = /^\d+$/.test(rawPage) ? Number(rawPage) : 1;
  const page =
    Number.isSafeInteger(candidate) &&
    candidate >= 1 &&
    candidate <= MAX_PUBLIC_JOBS_PAGE
      ? candidate
      : 1;
  const workplace = publicWorkplaceOptions.find(
    (value) => value === params.workplace,
  );
  const employment = publicEmploymentOptions.find(
    (value) => value === params.employment,
  );
  return {
    page,
    q: normalizedText(params.q),
    location: normalizedText(params.location),
    workplace,
    employment,
  };
}

export function buildPublicJobsHref(
  state: PublicJobsQueryState,
  changes: Partial<PublicJobsQueryState> = {},
): string {
  const changesFilters = ["q", "location", "workplace", "employment"].some(
    (key) => Object.hasOwn(changes, key),
  );
  const merged = {
    ...state,
    ...changes,
    page: changes.page ?? (changesFilters ? 1 : state.page),
  };
  const query = parsePublicJobsQuery({
    ...merged,
    page: String(merged.page),
  });
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.location) params.set("location", query.location);
  if (query.workplace) params.set("workplace", query.workplace);
  if (query.employment) params.set("employment", query.employment);
  if (query.page !== 1) params.set("page", String(query.page));
  return `/jobs${params.size ? `?${params}` : ""}`;
}

export function needsPublicJobsNormalization(
  raw: PublicJobsSearchParams,
  state: PublicJobsQueryState,
): boolean {
  const expected = new URLSearchParams(
    buildPublicJobsHref(state).split("?")[1],
  );
  const keys = Object.keys(raw);
  return (
    keys.length !== expected.size ||
    keys.some(
      (key) => typeof raw[key] !== "string" || raw[key] !== expected.get(key),
    )
  );
}

export function hasPublicJobsFilters(state: PublicJobsQueryState): boolean {
  return Boolean(
    state.q || state.location || state.workplace || state.employment,
  );
}

export function getPublicJobsPageCount(total: number): number {
  return Math.min(
    MAX_PUBLIC_JOBS_PAGE,
    Math.max(1, Math.ceil(total / PUBLIC_JOBS_PAGE_SIZE)),
  );
}
