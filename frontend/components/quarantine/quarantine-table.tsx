import Link from "next/link";
import type { QuarantineListItem } from "@/lib/api/types";
import {
  formatQuarantineTimestamp,
  getQuarantineCategoryLabel,
  truncateErrorMessage,
} from "@/lib/quarantine/presentation";
import { QuarantineStatusBadge } from "./quarantine-status-badge";
import { getSourceProviderLabel } from "@/lib/sources/presentation";

export function QuarantineTable({
  records,
}: {
  records: QuarantineListItem[];
}) {
  return (
    <div>
      <p className="mb-2 text-xs text-muted-foreground lg:hidden">
        Scroll the table to see all record details.
      </p>
      <div
        role="region"
        aria-label="Quarantine records table, horizontally scrollable"
        tabIndex={0}
        className="overflow-x-auto rounded-lg border border-border bg-card outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <table className="w-full min-w-[1080px] table-fixed text-left text-sm">
          <caption className="sr-only">
            Quarantined source records, ordered newest first, with processing
            errors and provenance.
          </caption>
          <thead className="border-b border-border bg-muted/40">
            <tr>
              {[
                ["Status", "w-[105px]"],
                ["Source", "w-[180px]"],
                ["External Job ID", "w-[160px]"],
                ["Error", "w-[300px]"],
                ["Run", "w-[110px]"],
                ["Created", "w-[190px]"],
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
            {records.map((record) => (
              <tr key={record.id} className="border-t border-border align-top">
                <td className="px-4 py-4">
                  <QuarantineStatusBadge status={record.status} />
                </td>
                <td className="px-4 py-4">
                  <Link
                    href={`/dashboard/sources/${record.source_connection_id}`}
                    prefetch={false}
                    className="break-words underline-offset-4 outline-none [overflow-wrap:anywhere] hover:text-primary hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {record.source.company_name}
                  </Link>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {getSourceProviderLabel(record.source.provider)}
                  </p>
                </td>
                <td className="px-4 py-4">
                  <p className="break-all font-mono text-xs">
                    {record.external_job_id ?? "—"}
                  </p>
                  {record.external_job_id === null && (
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Identity unavailable
                    </p>
                  )}
                  <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                    {record.raw_record_locator ?? "—"}
                  </p>
                </td>
                <td className="px-4 py-4">
                  <Link
                    href={`/dashboard/quarantine/${record.id}`}
                    prefetch={false}
                    className="break-words font-medium underline-offset-4 outline-none [overflow-wrap:anywhere] hover:text-primary hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label={`Inspect quarantined record: ${getQuarantineCategoryLabel(record.error_category)}`}
                  >
                    {getQuarantineCategoryLabel(record.error_category)}
                  </Link>
                  {record.error_code && (
                    <p className="mt-1.5 break-all font-mono text-xs text-muted-foreground">
                      {record.error_code}
                    </p>
                  )}
                  <p className="mt-1.5 break-words text-xs leading-5 text-muted-foreground [overflow-wrap:anywhere]">
                    {truncateErrorMessage(record.error_message)}
                  </p>
                </td>
                <td className="px-4 py-4">
                  <Link
                    href={`/dashboard/runs/${record.pipeline_run_id}?source=${record.source_connection_id}`}
                    prefetch={false}
                    title={record.pipeline_run_id}
                    aria-label={`Pipeline run ${record.pipeline_run_id}`}
                    className="font-mono text-xs text-primary underline-offset-4 outline-none hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {record.pipeline_run_id.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-4 py-4">
                  <time
                    dateTime={record.created_at}
                    className="text-xs leading-5"
                  >
                    {formatQuarantineTimestamp(record.created_at)}
                  </time>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
