import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { readPublicJobDetail } from "../lib/api/public-job-detail";
import { publicJobDetail } from "./public-jobs-fixtures";

function responseClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("detail loader returns real public data from only the public endpoint without persistent caching", async () => {
  const job = publicJobDetail();
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, options) => {
      assert.equal(
        new URL(String(input)).pathname,
        `/api/v1/public/jobs/${job.id}`,
      );
      assert.equal(options?.cache, "no-store");
      return Response.json(job);
    },
  });
  assert.deepEqual(await readPublicJobDetail(job.id, client), {
    state: "available",
    job,
  });
});

test("invalid and documented missing job identities become not-found outcomes", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      throw new Error("must not fetch invalid ID");
    },
  });
  assert.deepEqual(await readPublicJobDetail("invalid", client), {
    state: "not_found",
  });
  assert.deepEqual(
    await readPublicJobDetail(
      publicJobDetail().id,
      responseClient({ error: { code: "JOB_NOT_FOUND" } }, 404),
    ),
    { state: "not_found" },
  );
});

test("API failures and malformed/unsafe responses become unavailable, never false not-found or leaked diagnostics", async () => {
  const job = publicJobDetail();
  for (const client of [
    responseClient(
      { error: { code: "PRIVATE_DATABASE_ERROR", message: "private-token" } },
      500,
    ),
    responseClient(publicJobDetail({ source_url: "javascript:attack()" })),
    responseClient({ ...job, source_url: null }),
    responseClient({ error: { code: "PROXY_NOT_FOUND" } }, 404),
    new ApiClient({ baseUrl: "" }),
  ]) {
    assert.deepEqual(await readPublicJobDetail(job.id, client), {
      state: "unavailable",
    });
  }
});

test("unexpected programming errors reach the route boundary instead of being hidden", async () => {
  const client = responseClient(publicJobDetail());
  client.getJson = async () => {
    throw new TypeError("unexpected programming failure");
  };
  await assert.rejects(
    readPublicJobDetail(publicJobDetail().id, client),
    TypeError,
  );
});
