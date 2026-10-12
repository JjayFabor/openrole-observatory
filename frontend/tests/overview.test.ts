import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { getOverview } from "../lib/api/overview";
import { sourceHealth, sourceId, pipelineRun } from "./fixtures";

function overviewClient(failedPaths: string[] = [], sourceStatus = 200) {
  const requested: string[] = [];
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) => {
      const path = new URL(String(input)).pathname;
      requested.push(path);
      if (failedPaths.includes(path))
        throw new Error("Sensitive exception details");
      if (path === "/health") return Response.json({ status: "ok" });
      if (path === "/ready")
        return Response.json({ status: "ready", database: "available" });
      if (path === "/api/v1/pipeline-runs")
        return Response.json({ items: [pipelineRun()], limit: 5, offset: 0 });
      return Response.json(
        sourceStatus === 200
          ? sourceHealth()
          : { error: { code: "SOURCE_NOT_FOUND" } },
        { status: sourceStatus },
      );
    },
  });
  return { client, requested };
}

test("overview composes all successful backend sections", async () => {
  const { client, requested } = overviewClient();
  const result = await getOverview(client, sourceId);
  assert.deepEqual(result.system, { api: "healthy", database: "ready" });
  assert.deepEqual(result.source, {
    state: "available",
    source: sourceHealth(),
  });
  assert.deepEqual(result.runs, { state: "available", runs: [pipelineRun()] });
  assert.equal(requested.length, 4);
});

test("missing or whitespace source configuration makes no source HTTP call", async () => {
  for (const configured of ["", "   "]) {
    const { client, requested } = overviewClient();
    const result = await getOverview(client, configured);
    assert.deepEqual(result.source, { state: "unconfigured" });
    assert.equal(requested.length, 3);
    assert.ok(!requested.some((path) => path.startsWith("/api/v1/sources/")));
    assert.equal(result.runs.state, "available");
  }
});

test("source configuration is trimmed without hard-coded IDs", async () => {
  const { client } = overviewClient();
  assert.equal(
    (await getOverview(client, ` ${sourceId} `)).source.state,
    "available",
  );
});

test("invalid source configuration and missing source are isolated safe errors", async () => {
  const { client, requested } = overviewClient();
  assert.deepEqual((await getOverview(client, "invalid")).source, {
    state: "unavailable",
    reason: "invalid_configuration",
  });
  assert.equal(requested.length, 3);
  const missing = overviewClient([], 404);
  assert.deepEqual((await getOverview(missing.client, sourceId)).source, {
    state: "unavailable",
    reason: "not_found",
  });
});

test("each combination of endpoint failures preserves successful sections", async () => {
  const paths = [
    "/health",
    "/ready",
    `/api/v1/sources/${sourceId}`,
    "/api/v1/pipeline-runs",
  ];
  for (let failureMask = 0; failureMask < 16; failureMask++) {
    const failed = paths.filter((_path, index) => failureMask & (1 << index));
    const { client } = overviewClient(failed);
    const result = await getOverview(client, sourceId);
    assert.equal(
      result.system.api,
      failureMask & 1 ? "unavailable" : "healthy",
    );
    assert.equal(
      result.system.database,
      failureMask & 2 ? "unavailable" : "ready",
    );
    assert.equal(
      result.source.state,
      failureMask & 4 ? "unavailable" : "available",
    );
    assert.equal(
      result.runs.state,
      failureMask & 8 ? "unavailable" : "available",
    );
    assert.doesNotMatch(JSON.stringify(result), /Sensitive exception details/);
  }
});

test("independent requests are all initiated before waiting for any response", async () => {
  const releases: (() => void)[] = [];
  const { client: healthy } = overviewClient();
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) => {
      await new Promise<void>((resolve) => releases.push(resolve));
      const path = new URL(String(input)).pathname;
      const result = await healthy.getJson(path);
      return Response.json(result.body);
    },
  });
  const pending = getOverview(client, sourceId);
  assert.equal(releases.length, 4);
  releases.forEach((release) => release());
  const result = await pending;
  assert.equal(result.source.state, "available");
});
