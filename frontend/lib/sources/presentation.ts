import type { SourceHealth, SourceProvider } from "../api/types";
import { formatAbsoluteTimestamp } from "../dashboard/presentation";

export function getSourceProviderLabel(provider: SourceProvider): string {
  return provider === "greenhouse" ? "Greenhouse" : provider;
}

export function getSourceActiveLabel(active: boolean): string {
  return active ? "Active" : "Inactive";
}

export function isNeverSynchronized(
  source: Pick<
    SourceHealth,
    "last_attempted_sync_at" | "last_successful_sync_at"
  >,
): boolean {
  return (
    source.last_attempted_sync_at === null &&
    source.last_successful_sync_at === null
  );
}

export function formatSourceTimestamp(value: string | null): string {
  return value === null ? "—" : formatAbsoluteTimestamp(value);
}

export function getSafeCareersUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
