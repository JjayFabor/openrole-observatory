import Link from "next/link";
import type { SourceRead } from "@/lib/api/types";
import { PipelineStatusBadge } from "@/components/dashboard/pipeline-status-badge";
import {
  formatSourceTimestamp,
  getSourceProviderLabel,
  isNeverSynchronized,
} from "@/lib/sources/presentation";
import { SourceStatusBadge } from "./source-status-badge";

export function SourceTable({ sources }: { sources: SourceRead[] }) {
  return (
    <div>
      <p className="mb-2 text-xs text-muted-foreground">
        Scroll the table to see all source details.
      </p>
      <div
        role="region"
        aria-label="Sources table, horizontally scrollable"
        tabIndex={0}
        className="overflow-x-auto rounded-lg border border-border bg-card outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <table className="w-full min-w-[1320px] table-fixed text-left text-sm">
          <caption className="sr-only">
            Configured ATS sources, ordered by company name, with separate
            active state and latest run status.
          </caption>
          <thead className="border-b border-border bg-muted/40">
            <tr>
              {[
                ["Company", "w-[210px]"],
                ["Provider", "w-[110px]"],
                ["Active state", "w-[115px]"],
                ["Last attempted", "w-[190px]"],
                ["Last successful", "w-[190px]"],
                ["Latest run", "w-[210px]"],
                ["Fetched", "w-[90px]"],
                ["Quarantined", "w-[110px]"],
              ].map(([label, width]) => (
                <th
                  key={label}
                  scope="col"
                  className={`${width} whitespace-nowrap px-4 py-3 text-xs font-medium text-muted-foreground`}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.id} className="border-t border-border align-top">
                <td className="px-4 py-4">
                  <Link
                    href={`/dashboard/sources/${source.id}`}
                    prefetch={false}
                    className="break-words font-medium underline-offset-4 outline-none [overflow-wrap:anywhere] hover:text-primary hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {source.company.name}
                  </Link>
                  {isNeverSynchronized(source) && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Never synchronized
                    </p>
                  )}
                </td>
                <td className="px-4 py-4 text-xs">
                  {getSourceProviderLabel(source.provider)}
                </td>
                <td className="px-4 py-4">
                  <SourceStatusBadge active={source.is_active} />
                </td>
                <td className="px-4 py-4 text-xs leading-5">
                  {source.last_attempted_sync_at ? (
                    <time dateTime={source.last_attempted_sync_at}>
                      {formatSourceTimestamp(source.last_attempted_sync_at)}
                    </time>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-4 py-4 text-xs leading-5">
                  {source.last_successful_sync_at ? (
                    <time dateTime={source.last_successful_sync_at}>
                      {formatSourceTimestamp(source.last_successful_sync_at)}
                    </time>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-4 py-4">
                  {source.latest_run ? (
                    <Link
                      href={`/dashboard/runs/${source.latest_run.id}?source=${source.id}`}
                      prefetch={false}
                      aria-label={`Latest run for ${source.company.name}`}
                      className="inline-block rounded outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <PipelineStatusBadge status={source.latest_run.status} />
                    </Link>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      No runs yet
                    </span>
                  )}
                </td>
                <td className="px-4 py-4 text-xs tabular-nums">
                  {source.latest_run?.records_fetched ?? "—"}
                </td>
                <td className="px-4 py-4 text-xs tabular-nums">
                  {source.latest_run?.records_quarantined ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
