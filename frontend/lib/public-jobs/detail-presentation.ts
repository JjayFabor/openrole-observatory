import type {
  PublicJobDetail,
  PublicJobListItem,
} from "../api/public-jobs-types";
import { formatSalary } from "../jobs/presentation";

const knownCurrencies = new Set(Intl.supportedValuesOf("currency"));
const salaryPeriods = ["hour", "day", "week", "month", "year"];

export function getPublicLifecyclePresentation(job: PublicJobDetail) {
  const observed = job.lifecycle_status === "observed";
  return {
    observed,
    label: observed ? "Observed" : "Not currently observed",
    sourceAction: observed ? "View original listing" : "Check original source",
    absenceConfirmedAt: observed ? null : job.no_longer_observed_at,
    reappearedAt: observed ? job.reappeared_at : null,
  };
}

export function getPublicDetailSalary(
  job: Pick<
    PublicJobListItem,
    "salary_min" | "salary_max" | "salary_currency" | "salary_period"
  >,
): string | null {
  if (job.salary_min === null && job.salary_max === null) return null;
  const currency =
    job.salary_currency && knownCurrencies.has(job.salary_currency)
      ? job.salary_currency
      : null;
  const period =
    job.salary_period && salaryPeriods.includes(job.salary_period)
      ? job.salary_period
      : null;
  const amount = formatSalary({
    ...job,
    salary_currency: currency,
    salary_period: period,
  });
  const missingUnits = [
    !currency && "currency unavailable",
    !period && "period unavailable",
  ].filter(Boolean);
  return `${amount}${missingUnits.length ? ` (${missingUnits.join("; ")})` : ""}`;
}
