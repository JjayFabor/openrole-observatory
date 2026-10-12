import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import {
  getJob,
  getJobChanges,
  getJobLifecycle,
  getJobVersions,
} from "../lib/api/job-history";
import {
  jobChange,
  jobId,
  jobLifecycle,
  jobRead,
  jobVersion,
} from "./job-detail-fixtures";
function responseClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("job detail validates identity and exact Decimal strings without coercion", async () => {
  const job = jobRead({
    current_version: jobVersion({
      salary_min: "9007199254740993123.123456789",
      salary_max: null,
    }),
  });
  assert.deepEqual(await getJob(jobId, responseClient(job)), job);
  for (const overrides of [
    { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb" },
    { current_version: { ...job.current_version, salary_min: 120000 } },
    { current_version: { ...job.current_version, is_current: false } },
    { current_version: { ...job.current_version, canonical_metadata: [] } },
    { last_seen_at: "invalid" },
    { lifecycle_status: "closed" },
  ])
    await assert.rejects(
      getJob(jobId, responseClient({ ...job, ...overrides })),
      { code: "INVALID_RESPONSE" },
    );
});
test("job history uses 26th lookahead with 25-row offsets and no fabricated total", async () => {
  const items = Array.from({ length: 26 }, (_, index) =>
    jobVersion({
      id: `${String(index).padStart(8, "0")}-1111-4111-8111-111111111111`,
      version_number: index + 26,
      is_current: index === 25,
    }),
  );
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, init) => {
      assert.equal(
        String(input),
        `http://backend.test/api/v1/jobs/${jobId}/versions?limit=26&offset=25`,
      );
      assert.equal(init?.cache, "no-store");
      return Response.json({ items, limit: 26, offset: 25 });
    },
  });
  const page = await getJobVersions(jobId, 2, client);
  assert.equal(page.items.length, 25);
  assert.equal(page.hasNext, true);
  assert.equal("total" in page, false);
});
test("versions reject multiple current rows and malformed fields", async () => {
  const lookahead = Array.from({ length: 26 }, (_, index) =>
    jobVersion({
      version_number: index + 1,
      is_current: index === 0 || index === 25,
    }),
  );
  await assert.rejects(
    getJobVersions(
      jobId,
      1,
      responseClient({ items: lookahead, limit: 26, offset: 0 }),
    ),
    { code: "INVALID_RESPONSE" },
  );
  await assert.rejects(
    getJobVersions(
      jobId,
      1,
      responseClient({
        items: [jobVersion(), jobVersion({ version_number: 3 })],
        limit: 26,
        offset: 0,
      }),
    ),
    { code: "INVALID_RESPONSE" },
  );
  for (const overrides of [
    { version_number: 0 },
    { salary_max: "NaN" },
    { content_hash: "invalid" },
    { description: {} },
    { effective_from: null },
  ])
    await assert.rejects(
      getJobVersions(
        jobId,
        1,
        responseClient({
          items: [{ ...jobVersion(), ...overrides }],
          limit: 26,
          offset: 0,
        }),
      ),
      { code: "INVALID_RESPONSE" },
    );
});
test("change values preserve false/zero/null/objects and runtime shape is validated", async () => {
  const items = [
    jobChange({
      old_value: false,
      new_value: { zero: 0, nested: [null, false] },
    }),
  ];
  assert.deepEqual(
    await getJobChanges(
      jobId,
      1,
      responseClient({ items, limit: 26, offset: 0 }),
    ),
    { items, hasNext: false },
  );
  for (const overrides of [
    { change_type: "updated" },
    { to_version_id: "invalid" },
    { old_value: undefined },
    { detected_at: null },
  ])
    await assert.rejects(
      getJobChanges(
        jobId,
        1,
        responseClient({
          items: [{ ...jobChange(), ...overrides }],
          limit: 26,
          offset: 0,
        }),
      ),
      { code: "INVALID_RESPONSE" },
    );
});
test("lifecycle checks job identity and bounds its events independently", async () => {
  const summary = jobLifecycle();
  assert.deepEqual(await getJobLifecycle(jobId, 1, responseClient(summary)), {
    summary,
    hasNext: false,
  });
  for (const overrides of [
    { job_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb" },
    { events: [{ ...summary.events[0], event_type: "closed" }] },
    { offset: 25 },
    { current_status: "closed" },
  ])
    await assert.rejects(
      getJobLifecycle(jobId, 1, responseClient({ ...summary, ...overrides })),
      { code: "INVALID_RESPONSE" },
    );
});
test("invalid job IDs fail before HTTP and real 404 is preserved", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      assert.fail("Unexpected HTTP request");
    },
  });
  await assert.rejects(getJob("invalid", client), { code: "INVALID_JOB_ID" });
  await assert.rejects(
    getJob(jobId, responseClient({ error: { code: "JOB_NOT_FOUND" } }, 404)),
    { status: 404, code: "JOB_NOT_FOUND" },
  );
});
