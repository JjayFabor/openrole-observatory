import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { getSource, getSourceHealth, listSources } from "../lib/api/sources";
import { sourceRead } from "./source-fixtures";
import { sourceId } from "./fixtures";

function responseClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("source explorer requests bounded filtered pagination and preserves false", async () => {
  const source = sourceRead({ is_active: false });
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, options) => {
      assert.equal(
        String(input),
        "http://backend.test/api/v1/sources?limit=25&offset=25&is_active=false",
      );
      assert.equal(options?.cache, "no-store");
      return Response.json({
        items: [source],
        total: 26,
        limit: 25,
        offset: 25,
      });
    },
  });
  assert.deepEqual(await listSources({ page: 2, active: false }, client), {
    items: [source],
    total: 26,
    limit: 25,
    offset: 25,
  });
});

test("source detail projects only explicit safe fields and health stays backward-compatible", async () => {
  const source = sourceRead();
  const response = {
    ...source,
    configuration: { secret: "never-project" },
    external_account_key: "never-project",
    company: { ...source.company, private_info: "never-project" },
  };
  assert.deepEqual(await getSource(sourceId, responseClient(response)), source);
  const health = await getSourceHealth(sourceId, responseClient(response));
  assert.equal(health.id, source.id);
  assert.equal("company" in health, false);
  assert.doesNotMatch(JSON.stringify(health), /never-project/);
});

test("source explorer validates extended company, lineage, state and latest-run fields", async () => {
  for (const malformed of [
    null,
    { ...sourceRead(), company: null },
    { ...sourceRead(), company: { ...sourceRead().company, id: sourceId } },
    { ...sourceRead(), company: { ...sourceRead().company, domain: 1 } },
    { ...sourceRead(), provider: "lever" },
    { ...sourceRead(), is_active: "true" },
    { ...sourceRead(), latest_run: {} },
    {
      ...sourceRead(),
      id: "55555555-5555-4555-8555-555555555555",
      latest_run: null,
    },
    {
      ...sourceRead(),
      latest_run: {
        ...sourceRead().latest_run,
        source_connection_id: "55555555-5555-4555-8555-555555555555",
      },
    },
    { ...sourceRead(), last_successful_sync_at: "invalid" },
  ]) {
    await assert.rejects(getSource(sourceId, responseClient(malformed)), {
      code: "INVALID_RESPONSE",
    });
  }
});

test("never synchronized and empty pagination remain factual", async () => {
  const source = sourceRead({
    last_attempted_sync_at: null,
    last_successful_sync_at: null,
    latest_run: null,
  });
  assert.deepEqual(await getSource(sourceId, responseClient(source)), source);
  assert.deepEqual(
    await listSources(
      { page: 3 },
      responseClient({ items: [], total: 26, limit: 25, offset: 50 }),
    ),
    { items: [], total: 26, limit: 25, offset: 50 },
  );
});

test("source list rejects inconsistent envelopes and unsafe totals", async () => {
  for (const body of [
    { items: [], total: -1, limit: 25, offset: 0 },
    { items: [], total: 0, limit: 100, offset: 0 },
    { items: [], total: 0, limit: 25, offset: 25 },
    { items: [sourceRead()], total: 0, limit: 25, offset: 0 },
  ])
    await assert.rejects(listSources({ page: 1 }, responseClient(body)), {
      code: "INVALID_RESPONSE",
    });
});

test("source errors retain typed status and invalid UUID makes no request", async () => {
  await assert.rejects(
    getSource(
      sourceId,
      responseClient({ error: { code: "SOURCE_CONNECTION_NOT_FOUND" } }, 404),
    ),
    { name: "ApiError", status: 404 },
  );
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      assert.fail("Unexpected HTTP request");
    },
  });
  await assert.rejects(getSource("../source", client), {
    code: "INVALID_SOURCE_ID",
  });
});
