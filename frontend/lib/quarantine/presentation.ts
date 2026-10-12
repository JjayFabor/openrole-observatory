import type { JsonObject, QuarantineStatus } from "../api/types";
import { formatAbsoluteTimestamp } from "../dashboard/presentation";

export const quarantineCategories = [
  { value: "record_validation_failed", label: "Record validation" },
  {
    value: "duplicate_source_identifier",
    label: "Duplicate source identifier",
  },
  { value: "normalization_failed", label: "Normalization" },
  { value: "canonicalization_failed", label: "Canonicalization" },
  {
    value: "record_domain_validation_failed",
    label: "Record domain validation",
  },
] as const;

export function getQuarantineCategoryLabel(value: string): string {
  return (
    quarantineCategories.find((category) => category.value === value)?.label ??
    value
  );
}

export function getQuarantineStatusLabel(status: QuarantineStatus): string {
  return status === "open" ? "Open" : "Resolved";
}

export function getIdentityPresentation(externalId: string | null) {
  return externalId === null
    ? {
        label: "Identity unavailable",
        note: "Records without recoverable identity can prevent safe absence reconciliation.",
      }
    : {
        label: "Identity recoverable",
        note: "Recoverable identity can contribute presence evidence. Run-level safety is determined by the backend.",
      };
}

export function formatQuarantineTimestamp(value: string | null): string {
  return value === null ? "—" : formatAbsoluteTimestamp(value);
}

export function truncateErrorMessage(value: string, limit = 140): string {
  const characters = Array.from(value);
  return characters.length > limit
    ? `${characters.slice(0, limit).join("")}…`
    : value;
}

export function formatErrorDetails(details: JsonObject): string {
  return JSON.stringify(details, null, 2);
}
