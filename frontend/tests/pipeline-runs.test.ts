import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import {
  getPipelineRun,
  listPipelineRuns,
  listRuns,
} from "../lib/api/pipeline-runs";
import { pipelineStatuses } from "../lib/api/types";
import { pipelineRun } from "./fixtures";
import { sourceId } from "./fixtures";

test("source-scoped recent runs preserve five-row bound and validate scope before HTTP", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) => {
      assert.equal(
        String(input),
        `http://backend.test/api/v1/pipeline-runs?limit=5&offset=0&source_connection_id=${sourceId}`,
      );
      return Response.json({ items: [], limit: 5, offset: 0 });
    },
  });
  await listPipelineRuns(client, sourceId);
  await assert.rejects(
    listPipelineRuns(
      runsClient({
        items: [
          pipelineRun({
            source_connection_id: "33333333-3333-4333-8333-333333333333",
          }),
        ],
        limit: 5,
        offset: 0,
      }),
      sourceId,
    ),
    { code: "INVALID_RESPONSE" },
  );
  await assert.rejects(listPipelineRuns(client, "invalid"), {
    code: "INVALID_SOURCE_ID",
  });
});

function runsClient(payload: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(payload, { status }),
  });
}

test("recent runs requests the bounded global list and preserves all backend statuses", async () => {
  const items = pipelineStatuses.map((status) =>
    pipelineRun({
      status,
      completed_at:
        status === "running" || status === "pending"
          ? null
          : "2026-10-09T10:01:18Z",
    }),
  );
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, options) => {
      assert.equal(
        String(input),
        "http://backend.test/api/v1/pipeline-runs?limit=5&offset=0",
      );
      assert.equal(options?.cache, "no-store");
      return Response.json({ items, limit: 5, offset: 0 });
    },
  });
  assert.deepEqual(await listPipelineRuns(client), {
    items,
    limit: 5,
    offset: 0,
  });
});

test("empty run lists remain empty", async () => {
  assert.deepEqual(
    await listPipelineRuns(runsClient({ items: [], limit: 5, offset: 0 })),
    { items: [], limit: 5, offset: 0 },
  );
});

test("run validation rejects unsupported statuses, malformed timestamps, and invalid counters", async () => {
  for (const overrides of [
    { status: "success" },
    { started_at: "not-a-date" },
    { completed_at: "2026-10-09" },
    { created_at: null },
    { records_fetched: -1 },
    { records_valid: 1.5 },
    { records_quarantined: "2" },
    { jobs_new: null },
    { jobs_changed: Number.MAX_SAFE_INTEGER + 1 },
    { error_summary: {} },
    { id: "invalid" },
  ]) {
    const malformed = { ...pipelineRun(), ...overrides };
    await assert.rejects(
      listPipelineRuns(runsClient({ items: [malformed], limit: 5, offset: 0 })),
      { code: "INVALID_RESPONSE" },
    );
  }
});

test("run list pagination and shape are validated", async () => {
  for (const payload of [
    null,
    { items: null, limit: 5, offset: 0 },
    { items: [], limit: 100, offset: 0 },
    { items: [], limit: 5, offset: 1 },
    {
      items: Array.from({ length: 6 }, () => pipelineRun()),
      limit: 5,
      offset: 0,
    },
  ]) {
    await assert.rejects(listPipelineRuns(runsClient(payload)), {
      code: "INVALID_RESPONSE",
    });
  }
});

test("pipeline HTTP failures remain typed and do not become invented empty lists", async () => {
  await assert.rejects(
    listPipelineRuns(runsClient({ error: { code: "INTERNAL_ERROR" } }, 500)),
    { name: "ApiError", status: 500, code: "INTERNAL_ERROR" },
  );
});

test("runs explorer filters before pagination and uses26 lookahead for25 visible rows", async () => {
  const items = Array.from({ length: 26 }, (_, index) =>
    pipelineRun({
      id: `${String(index).padStart(8, "0")}-1111-4111-8111-111111111111`,
      status: "failed",
    }),
  );
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, init) => {
      assert.equal(
        String(input),
        `http://backend.test/api/v1/pipeline-runs?limit=26&offset=25&source_connection_id=${sourceId}&status=failed`,
      );
      assert.equal(init?.cache, "no-store");
      return Response.json({ items, limit: 26, offset: 25 });
    },
  });
  const result = await listRuns(
    { page: 2, source: sourceId, status: "failed" },
    client,
  );
  assert.equal(result.items.length, 25);
  assert.equal(result.hasNext, true);
  assert.equal("total" in result, false);
  await assert.rejects(
    listRuns(
      { page: 1, status: "failed" },
      runsClient({ items: [pipelineRun()], limit: 26, offset: 0 }),
    ),
    { code: "INVALID_RESPONSE" },
  );
});

test("runs explorer preserves genuine empty pages and rejects malformed envelopes", async () => {
  assert.deepEqual(
    await listRuns(
      { page: 2 },
      runsClient({ items: [], limit: 26, offset: 25 }),
    ),
    { items: [], hasNext: false },
  );
  for (const body of [
    { items: [], limit: 25, offset: 0 },
    { items: [], limit: 26, offset: 25 },
    {
      items: [{ ...pipelineRun(), records_valid: null }],
      limit: 26,
      offset: 0,
    },
  ])
    await assert.rejects(listRuns({ page: 1 }, runsClient(body)), {
      code: "INVALID_RESPONSE",
    });
});

test("run detail validates requested identity and primary failures", async () => {
  const run = pipelineRun();
  assert.deepEqual(await getPipelineRun(run.id, runsClient(run)), run);
  await assert.rejects(
    getPipelineRun(run.id, runsClient({ ...run, id: sourceId })),
    { code: "INVALID_RESPONSE" },
  );
  await assert.rejects(
    getPipelineRun(
      run.id,
      runsClient({ error: { code: "PIPELINE_RUN_NOT_FOUND" } }, 404),
    ),
    { status: 404 },
  );
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      assert.fail("Unexpected HTTP");
    },
  });
  await assert.rejects(getPipelineRun("invalid", client), {
    code: "INVALID_RUN_ID",
  });
});
