import type { PublicJobListItem } from "../api/public-jobs-types";
import {
  formatSalary,
  formatWorkplaceType,
  formatEmploymentType,
} from "../jobs/presentation";
import { publicWorkplaceOptions, publicEmploymentOptions } from "./query-state";

const knownCurrencies = new Set(Intl.supportedValuesOf("currency"));

export function getPublicJobTypes(job: PublicJobListItem): string | null {
  const workplace = publicWorkplaceOptions.some(
    (value) => value === job.workplace_type,
  )
    ? formatWorkplaceType(job.workplace_type)
    : null;
  const employment = publicEmploymentOptions.some(
    (value) => value === job.employment_type,
  )
    ? formatEmploymentType(job.employment_type)
    : null;
  return [workplace, employment].filter(Boolean).join(" · ") || null;
}

export function getPublicJobSalary(job: PublicJobListItem): string | null {
  if (
    (job.salary_min === null && job.salary_max === null) ||
    !job.salary_currency ||
    !knownCurrencies.has(job.salary_currency) ||
    !["hour", "day", "week", "month", "year"].includes(job.salary_period ?? "")
  ) {
    return null;
  }
  return formatSalary(job);
}
