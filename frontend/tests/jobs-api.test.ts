import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { listJobs } from "../lib/api/jobs";
import type { JobListItem } from "../lib/api/types";

const job: JobListItem = {
  id: "11111111-1111-4111-8111-111111111111",
  external_job_id: "gh-123",
  company: {
    id: "22222222-2222-4222-8222-222222222222",
    name: "Example Company",
  },
  source: {
    id: "33333333-3333-4333-8333-333333333333",
    provider: "greenhouse",
  },
  lifecycle_status: "observed",
  first_seen_at: "2026-10-01T10:00:00Z",
  last_seen_at: "2026-10-09T10:00:00Z",
  absence_first_detected_at: null,
  reappeared_at: null,
  consecutive_absent_runs: 0,
  current_version: {
    id: "44444444-4444-4444-8444-444444444444",
    version_number: 2,
    title: "Backend Engineer",
    location_text: "Remote",
    workplace_type: "remote",
    employment_type: "full_time",
  },
};

function jobsClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("jobs makes one uncached paginated read with exact backend filter names", async () => {
  let requests = 0;
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, options) => {
      requests++;
      const url = new URL(String(input));
      assert.equal(url.pathname, "/api/v1/jobs");
      assert.deepEqual(Object.fromEntries(url.searchParams), {
        limit: "25",
        offset: "25",
        lifecycle_status: "observed",
        source_connection_id: job.source.id,
        q: "Remote & Engineer",
      });
      assert.equal(options?.cache, "no-store");
      return Response.json({ items: [job], total: 26, limit: 25, offset: 25 });
    },
  });
  const result = await listJobs(
    {
      page: 2,
      status: "observed",
      source: job.source.id,
      q: "Remote & Engineer",
    },
    client,
  );
  assert.equal(requests, 1);
  assert.equal(result.total, 26);
  assert.deepEqual(result.items, [job]);
});

test("jobs retains backend lifecycle evidence and nullable canonical facts", async () => {
  const nullable = {
    ...job,
    lifecycle_status: "not_observed",
    absence_first_detected_at: "2026-10-09T11:00:00Z",
    reappeared_at: "2026-10-08T10:00:00Z",
    consecutive_absent_runs: 2,
    current_version: {
      ...job.current_version,
      location_text: null,
      workplace_type: null,
      employment_type: null,
    },
  };
  const result = await listJobs(
    { page: 1 },
    jobsClient({ items: [nullable], total: 1, limit: 25, offset: 0 }),
  );
  assert.deepEqual(result.items[0], nullable);
});

test("tentative absence remains observed without deriving a different status", async () => {
  const tentative = {
    ...job,
    consecutive_absent_runs: 1,
    absence_first_detected_at: "2026-10-09T11:00:00Z",
  };
  const result = await listJobs(
    { page: 1 },
    jobsClient({ items: [tentative], total: 1, limit: 25, offset: 0 }),
  );
  assert.equal(result.items[0].lifecycle_status, "observed");
});

test("empty lists retain the backend total and requested offset", async () => {
  assert.deepEqual(
    await listJobs(
      { page: 3 },
      jobsClient({ items: [], total: 26, limit: 25, offset: 50 }),
    ),
    { items: [], total: 26, limit: 25, offset: 50 },
  );
});

test("jobs validates current-version, safe relationship, lifecycle and timestamp contracts", async () => {
  for (const malformed of [
    null,
    { ...job, company: { id: job.company.id } },
    { ...job, source: { ...job.source, provider: "lever" } },
    { ...job, current_version: null },
    { ...job, current_version: { ...job.current_version, version_number: 0 } },
    { ...job, current_version: { ...job.current_version, title: null } },
    { ...job, lifecycle_status: "closed" },
    { ...job, last_seen_at: "bad" },
    { ...job, reappeared_at: "bad" },
    { ...job, consecutive_absent_runs: -1 },
  ]) {
    await assert.rejects(
      listJobs(
        { page: 1 },
        jobsClient({ items: [malformed], total: 1, limit: 25, offset: 0 }),
      ),
      { name: "ApiError", code: "INVALID_RESPONSE" },
    );
  }
});

test("jobs rejects inconsistent pagination envelopes and unsafe totals", async () => {
  for (const body of [
    { items: [], total: -1, limit: 25, offset: 0 },
    { items: [], total: 0, limit: 100, offset: 0 },
    { items: [], total: 0, limit: 25, offset: 25 },
    { items: [job], total: 0, limit: 25, offset: 0 },
    {
      items: Array.from({ length: 26 }, () => job),
      total: 26,
      limit: 25,
      offset: 0,
    },
  ]) {
    await assert.rejects(listJobs({ page: 1 }, jobsClient(body)), {
      code: "INVALID_RESPONSE",
    });
  }
});

test("jobs HTTP and network errors remain errors rather than empty datasets", async () => {
  await assert.rejects(
    listJobs(
      { page: 1 },
      jobsClient(
        { error: { code: "INTERNAL_ERROR", message: "Sensitive DB details" } },
        500,
      ),
    ),
    { name: "ApiError", status: 500, code: "INTERNAL_ERROR" },
  );
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      throw new Error("Private transport detail");
    },
  });
  await assert.rejects(listJobs({ page: 1 }, client), {
    name: "ApiError",
    code: "NETWORK_ERROR",
  });
});
