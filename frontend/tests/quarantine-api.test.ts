import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import {
  getQuarantineRecord,
  listQuarantineRecords,
} from "../lib/api/quarantine";
import {
  quarantineDetail,
  quarantineId,
  quarantineRecord,
  quarantineRunId,
  quarantineSourceId,
} from "./quarantine-fixtures";

function quarantineClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("source activity requests only five quarantine records and bounds custom limits", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) => {
      assert.equal(
        String(input),
        `http://backend.test/api/v1/quarantine?limit=5&offset=0&source_connection_id=${quarantineSourceId}`,
      );
      return Response.json({ items: [], total: 0, limit: 5, offset: 0 });
    },
  });
  await listQuarantineRecords(
    { page: 1, source: quarantineSourceId },
    client,
    5,
  );
  await assert.rejects(
    listQuarantineRecords(
      { page: 1, source: quarantineSourceId },
      quarantineClient({
        items: [quarantineRecord({ source_connection_id: quarantineRunId })],
        total: 1,
        limit: 5,
        offset: 0,
      }),
      5,
    ),
    { code: "INVALID_RESPONSE" },
  );
  for (const limit of [0, 101, 1.5])
    await assert.rejects(listQuarantineRecords({ page: 1 }, client, limit), {
      code: "INVALID_LIMIT",
    });
});

test("quarantine makes one bounded uncached list read with backend filter names", async () => {
  let requests = 0;
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, options) => {
      requests++;
      const url = new URL(String(input));
      assert.equal(url.pathname, "/api/v1/quarantine");
      assert.deepEqual(Object.fromEntries(url.searchParams), {
        limit: "25",
        offset: "25",
        status: "resolved",
        source_connection_id: quarantineSourceId,
        pipeline_run_id: quarantineRunId,
        error_category: "record_validation_failed",
      });
      assert.equal(options?.cache, "no-store");
      return Response.json({
        items: [quarantineRecord()],
        total: 26,
        limit: 25,
        offset: 25,
      });
    },
  });
  const result = await listQuarantineRecords(
    {
      page: 2,
      status: "resolved",
      source: quarantineSourceId,
      run: quarantineRunId,
      category: "record_validation_failed",
    },
    client,
  );
  assert.equal(requests, 1);
  assert.equal(result.total, 26);
});

test("quarantine detail preserves all nested JSON facts including false, zero and null", async () => {
  const detail = quarantineDetail();
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, options) => {
      assert.equal(
        String(input),
        `http://backend.test/api/v1/quarantine/${quarantineId}`,
      );
      assert.equal(options?.cache, "no-store");
      return Response.json(detail);
    },
  });
  assert.deepEqual(await getQuarantineRecord(quarantineId, client), detail);
});

test("quarantine detail rejects a different valid returned identifier", async () => {
  await assert.rejects(
    getQuarantineRecord(
      quarantineId,
      quarantineClient(quarantineDetail({ id: quarantineSourceId })),
    ),
    { code: "INVALID_RESPONSE" },
  );
});

test("null identity/locator/code and resolved-without-timestamp facts are preserved", async () => {
  const record = quarantineRecord({
    external_job_id: null,
    raw_record_locator: null,
    error_code: null,
    status: "resolved",
    resolved_at: null,
  });
  const result = await listQuarantineRecords(
    { page: 1 },
    quarantineClient({ items: [record], total: 1, limit: 25, offset: 0 }),
  );
  assert.deepEqual(result.items, [record]);
});

test("invalid detail identifiers fail before an HTTP request", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      assert.fail("Unexpected request");
    },
  });
  for (const recordId of [
    "invalid",
    "../record",
    "https://other.test",
    `${quarantineId}?x=1`,
  ]) {
    await assert.rejects(getQuarantineRecord(recordId, client), {
      code: "INVALID_RECORD_ID",
    });
  }
});

test("quarantine rejects malformed source, lineage, status and timestamp contracts", async () => {
  for (const malformed of [
    null,
    { ...quarantineRecord(), status: "dismissed" },
    {
      ...quarantineRecord(),
      source: { provider: "lever", company_name: "Example" },
    },
    { ...quarantineRecord(), pipeline_run_id: null },
    { ...quarantineRecord(), external_job_id: 1 },
    { ...quarantineRecord(), error_code: {} },
    { ...quarantineRecord(), created_at: "bad" },
    { ...quarantineRecord(), resolved_at: "yesterday" },
    { ...quarantineRecord(), raw_snapshot_id: "invalid" },
  ]) {
    await assert.rejects(
      listQuarantineRecords(
        { page: 1 },
        quarantineClient({
          items: [malformed],
          total: 1,
          limit: 25,
          offset: 0,
        }),
      ),
      { code: "INVALID_RESPONSE" },
    );
  }
});

test("detail requires an object for structured errors and rejects missing fields", async () => {
  for (const error_details of [null, [], false, 0, "text"]) {
    await assert.rejects(
      getQuarantineRecord(
        quarantineId,
        quarantineClient({ ...quarantineRecord(), error_details }),
      ),
      { code: "INVALID_RESPONSE" },
    );
  }
  await assert.rejects(
    getQuarantineRecord(quarantineId, quarantineClient(quarantineRecord())),
    { code: "INVALID_RESPONSE" },
  );
});

test("list validates pagination and accepts genuine empty/out-of-range results", async () => {
  assert.deepEqual(
    await listQuarantineRecords(
      { page: 3 },
      quarantineClient({ items: [], total: 26, limit: 25, offset: 50 }),
    ),
    { items: [], total: 26, limit: 25, offset: 50 },
  );
  for (const body of [
    { items: [], total: -1, limit: 25, offset: 0 },
    { items: [], total: 0, limit: 100, offset: 0 },
    { items: [], total: 0, limit: 25, offset: 25 },
    { items: [quarantineRecord()], total: 0, limit: 25, offset: 0 },
    {
      items: Array.from({ length: 26 }, () => quarantineRecord()),
      total: 26,
      limit: 25,
      offset: 0,
    },
  ]) {
    await assert.rejects(
      listQuarantineRecords({ page: 1 }, quarantineClient(body)),
      { code: "INVALID_RESPONSE" },
    );
  }
});

test("HTTP not-found/server errors retain typed status and never become empty data", async () => {
  await assert.rejects(
    getQuarantineRecord(
      quarantineId,
      quarantineClient({ error: { code: "QUARANTINE_RECORD_NOT_FOUND" } }, 404),
    ),
    { name: "ApiError", status: 404, code: "QUARANTINE_RECORD_NOT_FOUND" },
  );
  await assert.rejects(
    listQuarantineRecords(
      { page: 1 },
      quarantineClient(
        { error: { code: "INTERNAL_ERROR", message: "Sensitive exception" } },
        500,
      ),
    ),
    { name: "ApiError", status: 500 },
  );
});
