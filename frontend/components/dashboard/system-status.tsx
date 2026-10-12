import { Database, Server } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { SystemStatus as SystemStatusData } from "@/lib/api/types";

export function SystemStatus({ status }: { status: SystemStatusData }) {
  const apiHealthy = status.api === "healthy";
  const databaseReady = status.database === "ready";
  return (
    <section aria-labelledby="system-status">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="system-status" className="text-base font-semibold">
          System Status
        </h2>
        <p className="text-xs text-muted-foreground">Checked on page load</p>
      </div>
      <div className="grid rounded-lg border border-border bg-card sm:grid-cols-2">
        <div className="flex items-start gap-3 px-5 py-5">
          <Server
            className="mt-0.5 size-4 shrink-0 text-muted-foreground"
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-medium">Backend API</h3>
            {!apiHealthy && (
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                Backend unavailable. The health check could not be completed.
              </p>
            )}
          </div>
          <Badge
            className={
              apiHealthy
                ? "border-primary/20 bg-accent text-accent-foreground"
                : "border-border bg-muted text-muted-foreground"
            }
          >
            {apiHealthy ? "Healthy" : "Unavailable"}
          </Badge>
        </div>
        <div className="flex items-start gap-3 border-t border-border px-5 py-5 sm:border-l sm:border-t-0">
          <Database
            className="mt-0.5 size-4 shrink-0 text-muted-foreground"
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-medium">Database readiness</h3>
            {!databaseReady && (
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {status.database === "not_ready"
                  ? "The backend reports that the database is unavailable."
                  : "Readiness check unavailable. Database status could not be confirmed."}
              </p>
            )}
          </div>
          <Badge
            className={
              databaseReady
                ? "border-primary/20 bg-accent text-accent-foreground"
                : "border-border bg-muted text-muted-foreground"
            }
          >
            {databaseReady
              ? "Ready"
              : status.database === "not_ready"
                ? "Not ready"
                : "Unavailable"}
          </Badge>
        </div>
      </div>
    </section>
  );
}
