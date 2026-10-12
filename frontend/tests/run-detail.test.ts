import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { getRunDetail } from "../lib/api/run-detail";
import { pipelineRun, sourceId } from "./fixtures";
import { sourceRead } from "./source-fixtures";
const runId = pipelineRun().id;
function responseClient(primaryStatus = 200, sourceFails = false) {
  const paths: string[] = [];
  return {
    paths,
    api: new ApiClient({
      baseUrl: "http://backend.test",
      fetcher: async (input) => {
        const url = new URL(String(input));
        paths.push(url.pathname);
        if (url.pathname.includes("pipeline-runs"))
          return Response.json(
            primaryStatus === 200
              ? pipelineRun()
              : { error: { code: "PIPELINE_RUN_NOT_FOUND" } },
            { status: primaryStatus },
          );
        assert.equal(url.pathname, `/api/v1/sources/${sourceId}`);
        if (sourceFails) throw new Error("private-token");
        return Response.json(sourceRead());
      },
    }),
  };
}
test("run detail uses persisted source identity and real primary run metrics", async () => {
  const { api, paths } = responseClient();
  const result = await getRunDetail(runId, api);
  assert.deepEqual(result, {
    state: "available",
    run: pipelineRun(),
    source: { state: "available", data: sourceRead() },
  });
  assert.deepEqual(paths, [
    `/api/v1/pipeline-runs/${runId}`,
    `/api/v1/sources/${sourceId}`,
  ]);
});
test("optional source failure leaves run facts visible without sensitive errors", async () => {
  const result = await getRunDetail(runId, responseClient(200, true).api);
  assert.deepEqual(result, {
    state: "available",
    run: pipelineRun(),
    source: { state: "unavailable" },
  });
  assert.doesNotMatch(JSON.stringify(result), /private-token/);
});
test("primary missing/unavailable and invalid run ID prevent optional source reads", async () => {
  for (const [status, state] of [
    [404, "not_found"],
    [500, "unavailable"],
  ] as const) {
    const { api, paths } = responseClient(status);
    assert.deepEqual(await getRunDetail(runId, api), { state });
    assert.equal(paths.length, 1);
  }
  const { api, paths } = responseClient();
  assert.deepEqual(await getRunDetail("invalid", api), { state: "not_found" });
  assert.equal(paths.length, 0);
});
