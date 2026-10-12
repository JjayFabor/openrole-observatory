import "server-only";
import { ApiClient, ApiError } from "./client";
import { listPipelineRuns } from "./pipeline-runs";
import { getSourceHealth } from "./sources";
import { getSystemStatus } from "./system";
import type { OverviewData, SourceSection } from "./types";

export async function getOverview(
  client = new ApiClient(),
  configuredSourceId = process.env.OPENROLE_DEFAULT_SOURCE_ID,
): Promise<OverviewData> {
  const sourceId = configuredSourceId?.trim();
  const [system, source, runs] = await Promise.allSettled([
    getSystemStatus(client),
    sourceId ? getSourceHealth(sourceId, client) : Promise.resolve(null),
    listPipelineRuns(client),
  ]);

  let sourceSection: SourceSection;
  if (!sourceId) {
    sourceSection = { state: "unconfigured" };
  } else if (source.status === "fulfilled" && source.value) {
    sourceSection = { state: "available", source: source.value };
  } else {
    const error = source.status === "rejected" ? source.reason : undefined;
    sourceSection = {
      state: "unavailable",
      reason:
        error instanceof ApiError && error.status === 404
          ? "not_found"
          : error instanceof ApiError && error.code === "INVALID_SOURCE_ID"
            ? "invalid_configuration"
            : "request_failed",
    };
  }

  return {
    // One reference time keeps relative labels consistent throughout the server render.
    fetchedAt: Date.now(),
    system:
      system.status === "fulfilled"
        ? system.value
        : { api: "unavailable", database: "unavailable" },
    source: sourceSection,
    runs:
      runs.status === "fulfilled"
        ? { state: "available", runs: runs.value.items }
        : { state: "unavailable" },
  };
}
