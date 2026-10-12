import { RecentRuns } from "@/components/dashboard/recent-runs";
import { SourceHealthCard } from "@/components/dashboard/source-health-card";
import { SystemStatus } from "@/components/dashboard/system-status";
import { getOverview } from "@/lib/api/overview";

// Operational data stays request-time even when build-time configuration is absent.
export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const overview = await getOverview();
  const now = overview.fetchedAt;
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Monitor source freshness and recent ingestion activity.
        </p>
      </header>
      <SystemStatus status={overview.system} />
      <SourceHealthCard section={overview.source} now={now} />
      <RecentRuns section={overview.runs} now={now} />
    </div>
  );
}
