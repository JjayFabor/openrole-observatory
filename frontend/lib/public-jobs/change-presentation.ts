import type {
  PublicJobChange,
  PublicSalaryValue,
  PublicTextChangeField,
} from "../api/public-job-changes-types";
import {
  formatWorkplaceType,
  formatEmploymentType,
} from "../jobs/presentation";
import { getPublicDetailSalary } from "./detail-presentation";

const fieldLabels: Record<PublicJobChange["field"], string> = {
  title: "Title",
  location_text: "Location",
  city: "City",
  region: "Region",
  country_code: "Country code",
  workplace_type: "Workplace",
  employment_type: "Employment type",
  salary: "Salary",
  description: "Description",
};
const observedFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const knownCurrencies = new Set(Intl.supportedValuesOf("currency"));
const knownPeriods = ["hour", "day", "week", "month", "year"];

export function formatPublicChangeTimestamp(value: string): string {
  return `${observedFormatter.format(new Date(value))} UTC`;
}
export function getPublicChangeHeading(change: PublicJobChange): string {
  const verb =
    change.change_type === "added"
      ? "added"
      : change.change_type === "removed"
        ? "removed"
        : change.field === "description"
          ? "updated"
          : "changed";
  return `${fieldLabels[change.field]} ${verb}`;
}
export function formatPublicChangedText(
  field: PublicTextChangeField,
  value: string | null,
): string {
  if (value === null || value.trim() === "") return "Not stated";
  if (field === "workplace_type" || field === "employment_type") {
    const label =
      field === "workplace_type"
        ? formatWorkplaceType(value)
        : formatEmploymentType(value);
    return label === "—" ? "Unavailable" : label;
  }
  return value;
}
export function formatPublicChangedSalary(
  value: PublicSalaryValue | null,
): string {
  if (value === null) return "Not stated";
  const amount = getPublicDetailSalary({
    salary_min: value.min,
    salary_max: value.max,
    salary_currency: value.currency,
    salary_period: value.period,
  });
  if (amount !== null) return amount;
  const currency =
    value.currency === null
      ? "Not stated"
      : knownCurrencies.has(value.currency)
        ? value.currency
        : "Unavailable";
  const period =
    value.period === null
      ? "Not stated"
      : knownPeriods.includes(value.period)
        ? value.period
        : "Unavailable";
  return `Amount not stated · Currency: ${currency} · Period: ${period}`;
}
export function getPublicChangeValues(
  change: Exclude<PublicJobChange, { field: "description" }>,
): { before: string; after: string } {
  return change.field === "salary"
    ? {
        before: formatPublicChangedSalary(change.old_value),
        after: formatPublicChangedSalary(change.new_value),
      }
    : {
        before: formatPublicChangedText(change.field, change.old_value),
        after: formatPublicChangedText(change.field, change.new_value),
      };
}
