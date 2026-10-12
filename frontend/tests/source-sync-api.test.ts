import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { syncSource } from "../lib/api/source-sync";
import type { SourceSyncResponse } from "../lib/api/types";
import { sourceId } from "./fixtures";

function syncResult(
  overrides: Partial<SourceSyncResponse> = {},
): SourceSyncResponse {
  return {
    pipeline_run_id: "22222222-2222-4222-8222-222222222222",
    source_connection_id: sourceId,
    status: "completed",
    records_fetched: 3,
    records_valid: 3,
    records_quarantined: 0,
    jobs_new: 1,
    jobs_changed: 1,
    jobs_unchanged: 1,
    started_at: "2026-10-09T10:00:00Z",
    completed_at: "2026-10-09T10:01:00Z",
    ...overrides,
  };
}
function syncClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("source sync makes one uncached body-free POST to the existing endpoint", async () => {
  let requests = 0;
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, init) => {
      requests++;
      assert.equal(
        String(input),
        `http://backend.test/api/v1/sources/${sourceId}/sync`,
      );
      assert.equal(init?.method, "POST");
      assert.equal(init?.cache, "no-store");
      assert.equal(init?.body, undefined);
      return Response.json(syncResult());
    },
  });
  assert.deepEqual(await syncSource(sourceId, client), syncResult());
  assert.equal(requests, 1);
});

test("sync response accepts terminal outcomes and projects only safe contract fields", async () => {
  for (const status of [
    "completed",
    "completed_with_errors",
    "failed",
  ] as const) {
    const result = syncResult({
      status,
      records_quarantined: status === "completed_with_errors" ? 1 : 0,
    });
    assert.deepEqual(
      await syncSource(
        sourceId,
        syncClient({ ...result, private_token: "never-project" }),
      ),
      result,
    );
  }
});

test("lifecycle optional/null and explicit counters are preserved without arbitrary extras", async () => {
  const lifecycle = {
    performed: false,
    skipped_reason: "unidentified_quarantine_records" as const,
    tentative_absences_reset: 1,
    jobs_reappeared: 0,
    first_absences_detected: 0,
    jobs_confirmed_not_observed: 0,
  };
  for (const value of [null, lifecycle]) {
    const result = syncResult({ lifecycle: value });
    assert.deepEqual(await syncSource(sourceId, syncClient(result)), result);
  }
  const result = await syncSource(
    sourceId,
    syncClient(
      syncResult({
        lifecycle: {
          ...lifecycle,
          secret: "never-project",
        } as typeof lifecycle,
      }),
    ),
  );
  assert.deepEqual(result.lifecycle, lifecycle);
});

test("sync rejects invalid IDs before HTTP", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      assert.fail("Unexpected HTTP request");
    },
  });
  for (const id of ["invalid", "../source", `${sourceId}?secret=1`])
    await assert.rejects(syncSource(id, client), { code: "INVALID_SOURCE_ID" });
});

test("sync rejects nonterminal statuses, wrong source, invalid counters and timestamps", async () => {
  for (const overrides of [
    { status: "running" },
    { status: "pending" },
    { source_connection_id: "33333333-3333-4333-8333-333333333333" },
    { pipeline_run_id: "invalid" },
    { records_fetched: -1 },
    { records_valid: 0.5 },
    { jobs_changed: "1" },
    { jobs_unchanged: Number.MAX_SAFE_INTEGER + 1 },
    { started_at: "invalid" },
    { completed_at: null },
    { completed_at: "2026-10-09T09:00:00Z" },
    { lifecycle: { performed: "false" } },
    {
      lifecycle: {
        performed: false,
        skipped_reason: "unexpected",
        tentative_absences_reset: 0,
        jobs_reappeared: 0,
        first_absences_detected: 0,
        jobs_confirmed_not_observed: 0,
      },
    },
  ])
    await assert.rejects(
      syncSource(sourceId, syncClient({ ...syncResult(), ...overrides })),
      { code: "INVALID_RESPONSE" },
    );
});

test("HTTP errors retain only status and code and are never retried", async () => {
  let requests = 0;
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      requests++;
      return Response.json(
        {
          error: {
            code: "SOURCE_SYNC_ALREADY_RUNNING",
            message: "private-host-and-token",
            request_id: "private-id",
          },
        },
        { status: 409 },
      );
    },
  });
  await assert.rejects(syncSource(sourceId, client), (error: unknown) => {
    assert.ok(error instanceof Error);
    assert.doesNotMatch(error.message, /private/);
    return true;
  });
  assert.equal(requests, 1);
});
