import { renderToStaticMarkup } from "react-dom/server";
import {
  AppRouterContext,
  type AppRouterInstance,
} from "next/dist/shared/lib/app-router-context.shared-runtime";
import {
  SourceSyncButton,
  SourceSyncFeedback,
} from "../components/sources/source-sync-button";
import type { SourceSyncResponse } from "../lib/api/types";

const router: AppRouterInstance = {
  back() {},
  forward() {},
  refresh() {},
  push() {},
  replace() {},
  prefetch() {},
  bfcacheId: "fixture",
};
const result: SourceSyncResponse = {
  pipeline_run_id: "22222222-2222-4222-8222-222222222222",
  source_connection_id: "11111111-1111-4111-8111-111111111111",
  status: "completed",
  records_fetched: 3,
  records_valid: 2,
  records_quarantined: 1,
  jobs_new: 1,
  jobs_changed: 0,
  jobs_unchanged: 1,
  started_at: "2026-10-09T10:00:00Z",
  completed_at: "2026-10-09T10:01:00Z",
};
const render = (active: boolean) =>
  renderToStaticMarkup(
    <AppRouterContext.Provider value={router}>
      <SourceSyncButton
        sourceId={result.source_connection_id}
        active={active}
        syncAction={async () => ({ state: "result", result })}
      />
    </AppRouterContext.Provider>,
  );
process.stdout.write(
  JSON.stringify({
    idle: render(true),
    inactive: render(false),
    completed: renderToStaticMarkup(
      <SourceSyncFeedback outcome={{ state: "result", result }} />,
    ),
    partial: renderToStaticMarkup(
      <SourceSyncFeedback
        outcome={{
          state: "result",
          result: { ...result, status: "completed_with_errors" },
        }}
      />,
    ),
    failed: renderToStaticMarkup(
      <SourceSyncFeedback
        outcome={{ state: "result", result: { ...result, status: "failed" } }}
      />,
    ),
    error: renderToStaticMarkup(
      <SourceSyncFeedback
        outcome={{ state: "error", reason: "already_running", refresh: true }}
      />,
    ),
  }),
);
