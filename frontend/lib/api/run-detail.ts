import "server-only";
import { ApiClient, ApiError } from "./client";
import { getPipelineRun } from "./pipeline-runs";
import { getSource } from "./sources";
import { isUuid } from "./validation";
import type { PipelineRun, RunDetailResult } from "./types";

export async function getRunDetail(
  runId: string,
  client = new ApiClient(),
): Promise<RunDetailResult> {
  if (!isUuid(runId)) return { state: "not_found" };
  let run: PipelineRun;
  try {
    run = await getPipelineRun(runId, client);
  } catch (error) {
    return {
      state:
        error instanceof ApiError && error.status === 404
          ? "not_found"
          : "unavailable",
    };
  }
  const source = await getSource(run.source_connection_id, client).then(
    (data) => ({ state: "available" as const, data }),
    () => ({ state: "unavailable" as const }),
  );
  return { state: "available", run, source };
}
