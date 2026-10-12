import type { JobLifecycleStatus, JobChangeEvent } from "../api/types";

export function getLifecycleLabel(status: JobLifecycleStatus): string {
  return status === "observed" ? "Observed" : "Not observed";
}

const workplaceLabels: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
};
const employmentLabels: Record<string, string> = {
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Contract",
  temporary: "Temporary",
  internship: "Internship",
  volunteer: "Volunteer",
  other: "Other",
};

export function formatWorkplaceType(value: string | null): string {
  const label = value ? workplaceLabels[value] : undefined;
  return typeof label === "string" ? label : "—";
}

export function formatEmploymentType(value: string | null): string {
  const label = value ? employmentLabels[value] : undefined;
  return typeof label === "string" ? label : "—";
}

const fieldLabels: Record<string, string> = {
  title: "Title",
  description: "Description",
  location_text: "Location",
  city: "City",
  region: "Region",
  country_code: "Country code",
  workplace_type: "Workplace",
  employment_type: "Employment type",
  salary_min: "Minimum salary",
  salary_max: "Maximum salary",
  salary_currency: "Salary currency",
  salary_period: "Salary period",
  source_url: "Source URL",
  canonical_metadata: "Canonical metadata",
};
export function getChangeFieldLabel(value: string): string {
  return fieldLabels[value] ?? value;
}
export function getChangeTypeLabel(
  value: "added" | "removed" | "modified",
): string {
  return { added: "Added", removed: "Removed", modified: "Changed" }[value];
}
export function getLifecycleEventLabel(
  value: "absence_detected" | "not_observed_confirmed" | "reappeared",
): string {
  return {
    absence_detected: "Absence detected",
    not_observed_confirmed: "Not observed confirmed",
    reappeared: "Reappeared",
  }[value];
}

export function formatExactDecimal(value: string): string {
  const [integer, fractional = ""] = value.split(".");
  const sign = integer.startsWith("-") ? "-" : "";
  const digits = integer.replace(/^[+-]/, "").replace(/^0+(?=\d)/, "");
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const fraction = fractional.replace(/0+$/, "");
  return `${sign}${grouped}${fraction ? `.${fraction}` : ""}`;
}
export function formatSalary(salary: {
  salary_min: string | null;
  salary_max: string | null;
  salary_currency: string | null;
  salary_period: string | null;
}): string {
  const min =
    salary.salary_min === null ? null : formatExactDecimal(salary.salary_min);
  const max =
    salary.salary_max === null ? null : formatExactDecimal(salary.salary_max);
  if (min === null && max === null) return "—";
  const amount =
    min !== null && max !== null
      ? `${min} – ${max}`
      : min !== null
        ? `${min}+`
        : max;
  const currency = salary.salary_currency ? `${salary.salary_currency} ` : "";
  const periods: Record<string, string> = {
    hour: "hour",
    day: "day",
    week: "week",
    month: "month",
    year: "year",
  };
  const period = salary.salary_period
    ? ` / ${periods[salary.salary_period] ?? salary.salary_period}`
    : "";
  return `${min === null ? "Up to " : ""}${currency}${amount}${period}`;
}

export function groupJobChanges(items: JobChangeEvent[]) {
  const groups = new Map<
    string,
    { from: number; to: number; items: JobChangeEvent[] }
  >();
  for (const item of items) {
    const key = `${item.from_version_id}/${item.to_version_id}`;
    const group = groups.get(key) ?? {
      from: item.from_version_number,
      to: item.to_version_number,
      items: [],
    };
    group.items.push(item);
    groups.set(key, group);
  }
  return Array.from(groups.values());
}
