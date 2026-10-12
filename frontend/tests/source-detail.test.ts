import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { getSourceDetail } from "../lib/api/source-detail";
import { sourceRead } from "./source-fixtures";
import { pipelineRun, sourceId } from "./fixtures";
import { quarantineRecord } from "./quarantine-fixtures";

function detailClient(failed: string[] = [], primaryStatus = 200) {
  const paths: string[] = [];
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) => {
      const url = new URL(String(input));
      paths.push(url.pathname);
      if (failed.includes(url.pathname))
        throw new Error("Sensitive exception details");
      if (url.pathname.startsWith("/api/v1/sources/"))
        return Response.json(
          primaryStatus === 200
            ? sourceRead()
            : { error: { code: "SOURCE_CONNECTION_NOT_FOUND" } },
          { status: primaryStatus },
        );
      assert.equal(url.searchParams.get("limit"), "5");
      assert.equal(url.searchParams.get("offset"), "0");
      assert.equal(url.searchParams.get("source_connection_id"), sourceId);
      return url.pathname.endsWith("pipeline-runs")
        ? Response.json({ items: [pipelineRun()], limit: 5, offset: 0 })
        : Response.json({
            items: [quarantineRecord({ source_connection_id: sourceId })],
            total: 1,
            limit: 5,
            offset: 0,
          });
    },
  });
  return { client, paths };
}

test("source detail composes primary and bounded source-specific histories", async () => {
  const { client, paths } = detailClient();
  const result = await getSourceDetail(sourceId, client);
  assert.equal(result.state, "available");
  if (result.state !== "available") assert.fail("Missing source detail");
  assert.deepEqual(result.source, sourceRead());
  assert.equal(result.runs.state, "available");
  assert.equal(result.quarantine.state, "available");
  assert.equal(paths.length, 3);
});

test("primary missing/error or invalid UUID prevents secondary reads", async () => {
  const missing = detailClient([], 404);
  assert.deepEqual(await getSourceDetail(sourceId, missing.client), {
    state: "not_found",
  });
  assert.equal(missing.paths.length, 1);
  const unavailable = detailClient([], 500);
  assert.deepEqual(await getSourceDetail(sourceId, unavailable.client), {
    state: "unavailable",
  });
  assert.equal(unavailable.paths.length, 1);
  const invalid = detailClient();
  assert.deepEqual(await getSourceDetail("invalid", invalid.client), {
    state: "not_found",
  });
  assert.equal(invalid.paths.length, 0);
});

test("secondary failures settle independently without exposing exceptions", async () => {
  for (let mask = 0; mask < 4; mask++) {
    const failed = ["/api/v1/pipeline-runs", "/api/v1/quarantine"].filter(
      (_path, index) => mask & (1 << index),
    );
    const { client } = detailClient(failed);
    const result = await getSourceDetail(sourceId, client);
    assert.equal(result.state, "available");
    if (result.state !== "available") assert.fail("Missing primary source");
    assert.equal(result.runs.state, mask & 1 ? "unavailable" : "available");
    assert.equal(
      result.quarantine.state,
      mask & 2 ? "unavailable" : "available",
    );
    assert.doesNotMatch(JSON.stringify(result), /Sensitive exception details/);
  }
});

test("secondary requests run concurrently after the primary succeeds", async () => {
  const releases: (() => void)[] = [];
  let signalStarted: (() => void) | undefined;
  const started = new Promise<void>((resolve) => {
    signalStarted = resolve;
  });
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) => {
      const url = new URL(String(input));
      if (url.pathname.startsWith("/api/v1/sources/"))
        return Response.json(sourceRead());
      await new Promise<void>((resolve) => {
        releases.push(resolve);
        if (releases.length === 2) signalStarted?.();
      });
      return url.pathname.endsWith("pipeline-runs")
        ? Response.json({ items: [], limit: 5, offset: 0 })
        : Response.json({ items: [], total: 0, limit: 5, offset: 0 });
    },
  });
  const pending = getSourceDetail(sourceId, client);
  await started;
  assert.equal(releases.length, 2);
  releases.forEach((release) => release());
  assert.equal((await pending).state, "available");
});
