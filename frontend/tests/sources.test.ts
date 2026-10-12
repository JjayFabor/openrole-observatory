import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { getSourceHealth } from "../lib/api/sources";
import { pipelineRun, sourceHealth, sourceId } from "./fixtures";

function sourceClient(payload: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(payload, { status }),
  });
}

test("source health uses the actual backend route and consumes its fields", async () => {
  const source = sourceHealth();
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, options) => {
      assert.equal(
        String(input),
        `http://backend.test/api/v1/sources/${sourceId}`,
      );
      assert.equal(options?.cache, "no-store");
      return Response.json(source);
    },
  });
  assert.deepEqual(await getSourceHealth(sourceId, client), source);
});

test("inactive and never-synchronized sources preserve null facts", async () => {
  const source = sourceHealth({
    is_active: false,
    last_attempted_sync_at: null,
    last_successful_sync_at: null,
    latest_run: null,
  });
  assert.deepEqual(
    await getSourceHealth(sourceId, sourceClient(source)),
    source,
  );
});

test("invalid source identifiers fail before any HTTP request", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      assert.fail("Unexpected request");
    },
  });
  for (const id of [
    "",
    "http://other.test",
    "../source",
    `${sourceId}?secret=1`,
    "invalid-uuid",
  ]) {
    await assert.rejects(getSourceHealth(id, client), {
      code: "INVALID_SOURCE_ID",
    });
  }
});

test("source validation rejects malformed native fields and latest runs", async () => {
  for (const payload of [
    null,
    { ...sourceHealth(), provider: "lever" },
    { ...sourceHealth(), is_active: "true" },
    { ...sourceHealth(), last_attempted_sync_at: "yesterday" },
    { ...sourceHealth(), last_successful_sync_at: undefined },
    { ...sourceHealth(), latest_run: {} },
    { ...sourceHealth(), company_id: "not-uuid" },
  ]) {
    await assert.rejects(getSourceHealth(sourceId, sourceClient(payload)), {
      code: "INVALID_RESPONSE",
    });
  }
});

test("source HTTP failures reuse the existing typed API error", async () => {
  await assert.rejects(
    getSourceHealth(
      sourceId,
      sourceClient(
        { error: { code: "SOURCE_NOT_FOUND", message: "Not found" } },
        404,
      ),
    ),
    { name: "ApiError", status: 404, code: "SOURCE_NOT_FOUND" },
  );
});

test("source health rejects another source ID and unrelated latest run", async () => {
  const other = "55555555-5555-4555-8555-555555555555";
  for (const source of [
    sourceHealth({ id: other }),
    sourceHealth({ latest_run: pipelineRun({ source_connection_id: other }) }),
  ])
    await assert.rejects(getSourceHealth(sourceId, sourceClient(source)), {
      code: "INVALID_RESPONSE",
    });
});
