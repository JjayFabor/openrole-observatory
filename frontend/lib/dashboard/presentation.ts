import type { PipelineRun, PipelineStatus } from "../api/types";

const statusPresentations = {
  pending: {
    label: "Pending",
    className: "border-border bg-card text-muted-foreground",
  },
  running: {
    label: "Running",
    className: "border-border bg-muted text-foreground",
  },
  completed: {
    label: "Completed",
    className: "border-primary/20 bg-accent text-accent-foreground",
  },
  completed_with_errors: {
    label: "Completed with errors",
    className: "border-amber-200 bg-amber-50 text-amber-900",
  },
  failed: {
    label: "Failed",
    className: "border-red-200 bg-red-50 text-red-800",
  },
} satisfies Record<PipelineStatus, { label: string; className: string }>;

export function getPipelineStatusPresentation(status: PipelineStatus) {
  return statusPresentations[status];
}

const absoluteFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});
const relativeFormatter = new Intl.RelativeTimeFormat("en-US", {
  numeric: "always",
  style: "short",
});

export function formatAbsoluteTimestamp(value: string | null): string {
  if (value === null) return "Never";
  const parsed = Date.parse(value);
  return Number.isFinite(parsed)
    ? `${absoluteFormatter.format(parsed)} UTC`
    : "Unavailable";
}

export function formatRelativeTimestamp(
  value: string | null,
  now: number,
): string {
  if (value === null) return "Never";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed) || !Number.isFinite(now)) return "Unavailable";
  const seconds = (parsed - now) / 1000;
  const magnitude = Math.abs(seconds);
  if (magnitude < 60)
    return relativeFormatter.format(Math.round(seconds), "second");
  if (magnitude < 3600)
    return relativeFormatter.format(Math.round(seconds / 60), "minute");
  if (magnitude < 86400)
    return relativeFormatter.format(Math.round(seconds / 3600), "hour");
  return relativeFormatter.format(Math.round(seconds / 86400), "day");
}

export function formatRunDuration(
  run: Pick<PipelineRun, "status" | "started_at" | "completed_at">,
): string {
  if (run.status === "running") return "Running";
  if (run.status === "pending") return "—";
  if (!run.completed_at) return "Unavailable";
  const milliseconds =
    Date.parse(run.completed_at) - Date.parse(run.started_at);
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "Unavailable";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60000)
    return `${Number((milliseconds / 1000).toFixed(1))} s`;
  const seconds = Math.round(milliseconds / 1000);
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
