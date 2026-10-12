import "server-only";
import { ApiClient, ApiError } from "./client";
import { getSource } from "./sources";
import { listPipelineRuns } from "./pipeline-runs";
import { listQuarantineRecords } from "./quarantine";
import { isUuid } from "./validation";
import type { SourceDetailResult, SourceRead } from "./types";

export async function getSourceDetail(
  sourceId: string,
  client = new ApiClient(),
): Promise<SourceDetailResult> {
  if (!isUuid(sourceId)) return { state: "not_found" };
  let source: SourceRead;
  try {
    source = await getSource(sourceId, client);
  } catch (error) {
    return {
      state:
        error instanceof ApiError && error.status === 404
          ? "not_found"
          : "unavailable",
    };
  }
  const [runs, quarantine] = await Promise.allSettled([
    listPipelineRuns(client, sourceId),
    listQuarantineRecords({ page: 1, source: sourceId }, client, 5),
  ]);
  return {
    state: "available",
    source,
    fetchedAt: Date.now(),
    runs:
      runs.status === "fulfilled"
        ? { state: "available", runs: runs.value.items }
        : { state: "unavailable" },
    quarantine:
      quarantine.status === "fulfilled"
        ? { state: "available", records: quarantine.value.items }
        : { state: "unavailable" },
  };
}
