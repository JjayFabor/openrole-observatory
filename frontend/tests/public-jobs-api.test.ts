import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { getPublicJob, listPublicJobs } from "../lib/api/public-jobs";
import { parsePublicJobsQuery } from "../lib/public-jobs/query-state";
import { publicJob, publicJobDetail } from "./public-jobs-fixtures";

function responseClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("list calls only the public endpoint with translated filters, backend pagination, and no-store", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test/prefix",
    fetcher: async (input, options) => {
      const url = new URL(String(input));
      assert.equal(url.pathname, "/prefix/api/v1/public/jobs");
      assert.deepEqual(Object.fromEntries(url.searchParams), {
        limit: "25",
        offset: "25",
        q: "Backend %_",
        location: "Berlin",
        workplace_type: "remote",
        employment_type: "full_time",
      });
      assert.equal(options?.cache, "no-store");
      assert.equal(options?.method, "GET");
      return Response.json({
        items: [publicJob()],
        total: 26,
        limit: 25,
        offset: 25,
      });
    },
  });
  const response = await listPublicJobs(
    parsePublicJobsQuery({
      q: " Backend %_ ",
      location: "Berlin",
      workplace: "remote",
      employment: "full_time",
      page: "2",
    }),
    client,
  );
  assert.equal(response.total, 26);
});

test("public boundary projects away unexpected internal fields without sorting or lifecycle refiltering", async () => {
  const item = {
    ...publicJob(),
    description: "private",
    lifecycle_status: "not_observed",
    configuration: { secret: "private-token" },
    source: {
      provider: "greenhouse",
      id: "source-id",
      external_account_key: "private-token",
    },
    company: { name: "Employer", domain: null, id: "company-id" },
  };
  const older = publicJob({
    id: "44444444-4444-4444-8444-444444444444",
    last_seen_at: "2026-10-01T00:00:00Z",
  });
  const response = await listPublicJobs(
    { page: 1 },
    responseClient({ items: [older, item], total: 2, limit: 25, offset: 0 }),
  );
  assert.deepEqual(
    response.items.map((job) => job.id),
    [older.id, item.id],
  );
  assert.doesNotMatch(
    JSON.stringify(response),
    /private-token|company-id|source-id|description|configuration|lifecycle_status/,
  );
});

test("strict public item validation rejects missing nullable fields, malformed timestamps, and floating-point salary", async () => {
  const missing: Record<string, unknown> = { ...publicJob() };
  delete missing.city;
  for (const item of [
    missing,
    publicJob({ last_seen_at: "yesterday" }),
    { ...publicJob(), salary_min: 90000 },
    publicJob({ salary_max: "NaN" }),
    { ...publicJob(), company: { name: "Employer" } },
  ]) {
    await assert.rejects(
      listPublicJobs(
        { page: 1 },
        responseClient({ items: [item], total: 1, limit: 25, offset: 0 }),
      ),
      { code: "INVALID_RESPONSE" },
    );
  }
  const unknownTypes = publicJob({
    workplace_type: "unmapped_workplace",
    employment_type: "unmapped_employment",
  });
  assert.equal(
    (
      await listPublicJobs(
        { page: 1 },
        responseClient({
          items: [unknownTypes],
          total: 1,
          limit: 25,
          offset: 0,
        }),
      )
    ).items[0].workplace_type,
    "unmapped_workplace",
  );
});

test("pagination is validated but a concurrently empty page remains a successful read", async () => {
  for (const body of [
    { items: [], total: -1, limit: 25, offset: 25 },
    { items: [], total: 40, limit: 10, offset: 25 },
    { items: [], total: 40, limit: 25, offset: 0 },
    {
      items: Array.from({ length: 26 }, () => publicJob()),
      total: 40,
      limit: 25,
      offset: 25,
    },
  ]) {
    await assert.rejects(listPublicJobs({ page: 2 }, responseClient(body)), {
      code: "INVALID_RESPONSE",
    });
  }
  assert.deepEqual(
    await listPublicJobs(
      { page: 2 },
      responseClient({ items: [], total: 40, limit: 25, offset: 25 }),
    ),
    { items: [], total: 40, limit: 25, offset: 25 },
  );
});

test("detail projects safe public fields and keeps known historical jobs addressable", async () => {
  const payload = {
    ...publicJobDetail({
      lifecycle_status: "not_observed",
      description: "<script>untrusted()</script>",
    }),
    content_hash: "private-hash",
    pipeline_run_id: "private-run",
  };
  const detail = await getPublicJob(payload.id, responseClient(payload));
  assert.equal(detail?.lifecycle_status, "not_observed");
  assert.equal(detail?.description, "<script>untrusted()</script>");
  assert.doesNotMatch(JSON.stringify(detail), /private-hash|private-run/);
});

test("invalid identifiers avoid fetching and documented unknown jobs return null", async () => {
  const neverFetch = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      throw new Error("must not fetch");
    },
  });
  assert.equal(await getPublicJob("not-a-uuid", neverFetch), null);
  assert.equal(
    await getPublicJob(
      publicJob().id,
      responseClient({ error: { code: "JOB_NOT_FOUND" } }, 404),
    ),
    null,
  );
  await assert.rejects(
    getPublicJob(
      publicJob().id,
      responseClient({ error: { code: "PROXY_MISSING" } }, 404),
    ),
    { code: "INVALID_RESPONSE" },
  );
});

test("detail rejects wrong identities, unsafe source/careers URLs, and absent lifecycle timestamps", async () => {
  const missing: Record<string, unknown> = { ...publicJobDetail() };
  delete missing.reappeared_at;
  for (const payload of [
    publicJobDetail({ id: "44444444-4444-4444-8444-444444444444" }),
    publicJobDetail({ source_url: "javascript:attack()" }),
    publicJobDetail({ source_url: "https://user:secret@example.test/jobs" }),
    publicJobDetail({
      company: {
        name: "Employer",
        domain: null,
        careers_url: "//example.test",
      },
    }),
    missing,
  ]) {
    await assert.rejects(
      getPublicJob(publicJob().id, responseClient(payload)),
      { code: "INVALID_RESPONSE" },
    );
  }
});

test("backend failures remain errors rather than empty listings or leaked response messages", async () => {
  const client = responseClient(
    {
      error: {
        code: "PUBLIC_JOBS_UNAVAILABLE",
        message: "postgres private-token",
      },
    },
    500,
  );
  await assert.rejects(
    listPublicJobs({ page: 1 }, client),
    (error: unknown) => {
      assert.ok(error instanceof Error);
      assert.doesNotMatch(error.message, /postgres|private-token/);
      return true;
    },
  );
});
