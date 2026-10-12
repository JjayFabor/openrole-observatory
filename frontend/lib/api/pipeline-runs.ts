import "server-only";
import { ApiClient, ApiError } from "./client";
import type {
  HistoryPage,
  PipelineRun,
  PipelineRunListResponse,
  PipelineStatus,
} from "./types";
import { isPipelineRun, isRecord, isUuid } from "./validation";
import {
  parseRunsQuery,
  RUNS_PAGE_SIZE,
  RUNS_READ_LIMIT,
  type RunsQueryState,
} from "../runs/query-state";

export async function listPipelineRuns(
  client = new ApiClient(),
  sourceId?: string,
): Promise<PipelineRunListResponse> {
  return readRunList(5, 0, client, sourceId);
}

async function readRunList(
  limit: number,
  offset: number,
  client: ApiClient,
  sourceId?: string,
  runStatus?: PipelineStatus,
): Promise<PipelineRunListResponse> {
  if (sourceId !== undefined && !isUuid(sourceId))
    throw new ApiError(0, "INVALID_SOURCE_ID");
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (sourceId) params.set("source_connection_id", sourceId);
  if (runStatus) params.set("status", runStatus);
  const { status, body } = await client.getJson(
    `/api/v1/pipeline-runs?${params}`,
  );
  if (
    status !== 200 ||
    !isRecord(body) ||
    body.limit !== limit ||
    body.offset !== offset ||
    !Array.isArray(body.items) ||
    body.items.length > limit ||
    !body.items.every(isPipelineRun) ||
    (sourceId !== undefined &&
      body.items.some(
        (run) =>
          run.source_connection_id.toLowerCase() !== sourceId.toLowerCase(),
      )) ||
    (runStatus !== undefined &&
      body.items.some((run) => run.status !== runStatus))
  ) {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  return { items: body.items, limit: body.limit, offset: body.offset };
}

export async function listRuns(
  state: RunsQueryState,
  client = new ApiClient(),
): Promise<HistoryPage<PipelineRun>> {
  const safe = parseRunsQuery({
    page: String(state.page),
    source: state.source,
    status: state.status,
  });
  const result = await readRunList(
    RUNS_READ_LIMIT,
    (safe.page - 1) * RUNS_PAGE_SIZE,
    client,
    safe.source,
    safe.status,
  );
  return {
    items: result.items.slice(0, RUNS_PAGE_SIZE),
    hasNext: result.items.length > RUNS_PAGE_SIZE,
  };
}

export async function getPipelineRun(
  runId: string,
  client = new ApiClient(),
): Promise<PipelineRun> {
  if (!isUuid(runId)) throw new ApiError(0, "INVALID_RUN_ID");
  const { status, body } = await client.getJson(
    `/api/v1/pipeline-runs/${runId}`,
  );
  if (
    status !== 200 ||
    !isPipelineRun(body) ||
    body.id.toLowerCase() !== runId.toLowerCase()
  )
    throw new ApiError(status, "INVALID_RESPONSE");
  return body;
}
