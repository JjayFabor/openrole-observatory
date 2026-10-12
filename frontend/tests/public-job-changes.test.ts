import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { listPublicJobChanges } from "../lib/api/public-job-changes";
import { publicJob } from "./public-jobs-fixtures";

const jobId = publicJob().id;
const textChange = {
  field: "workplace_type",
  change_type: "modified",
  old_value: "remote",
  new_value: "hybrid",
};
const group = { observed_at: "2026-10-12T00:00:00Z", changes: [textChange] };
const response = (items: unknown[]) => ({ job_id: jobId, items, limit: 10 });
function responseClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("changes read uses only its public endpoint, fixed group limit, and no-store", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, options) => {
      const url = new URL(String(input));
      assert.equal(url.pathname, `/api/v1/public/jobs/${jobId}/changes`);
      assert.deepEqual(Object.fromEntries(url.searchParams), { limit: "10" });
      assert.equal(options?.cache, "no-store");
      assert.equal(options?.method, "GET");
      return Response.json(response([group, group]));
    },
  });
  const result = await listPublicJobChanges(jobId, client);
  assert.equal(result.items.length, 2);
  assert.deepEqual(result.items[0], result.items[1]);
});

test("explicit public projection removes nested internal keys and historical description bodies", async () => {
  const salary = {
    min: "0.00",
    max: "9007199254740993.01",
    currency: "USD",
    period: "year",
    raw_metadata: "private-value",
  };
  const payload = {
    ...response([
      {
        ...group,
        to_version_id: "private-version",
        changes: [
          { ...textChange, pipeline_run_id: "private-run" },
          {
            field: "salary",
            change_type: "added",
            old_value: null,
            new_value: salary,
            source_observation_id: "private-observation",
          },
          {
            field: "description",
            change_type: "modified",
            old_value: "<script>private-old()</script>",
            new_value: "<p>private-new</p>",
          },
        ],
      },
    ]),
    configuration: "private-top",
  };
  const result = await listPublicJobChanges(jobId, responseClient(payload));
  assert.doesNotMatch(
    JSON.stringify(result),
    /private-|raw_metadata|version_id|pipeline_run_id|source_observation_id|configuration|<script|<p>/,
  );
  assert.deepEqual(result.items[0].changes[2], {
    field: "description",
    change_type: "modified",
  });
});

test("identity, group limit, chronological ordering and timestamp validity are checked", async () => {
  for (const payload of [
    { ...response([]), job_id: "44444444-4444-4444-8444-444444444444" },
    { ...response([]), limit: 50 },
    response(Array.from({ length: 11 }, () => group)),
    response([{ ...group, observed_at: "2026-10-11T00:00:00Z" }, group]),
    response([{ ...group, observed_at: "2026-02-30T00:00:00Z" }]),
    response([{ ...group, observed_at: "2026-10-12T00:00:00" }]),
  ]) {
    await assert.rejects(listPublicJobChanges(jobId, responseClient(payload)), {
      code: "INVALID_RESPONSE",
    });
  }
  const mixedCaseId = "abcdefab-cdef-4abc-8abc-abcdefabcdef";
  assert.equal(
    (
      await listPublicJobChanges(
        mixedCaseId.toUpperCase(),
        responseClient({ ...response([]), job_id: mixedCaseId }),
      )
    ).items.length,
    0,
  );
});

test("groups require unique allowed meanings and typed text values instead of generic JSON", async () => {
  for (const changes of [
    [],
    [textChange, textChange],
    [{ ...textChange, field: "source_url" }],
    [{ ...textChange, field: "canonical_metadata" }],
    [{ ...textChange, old_value: { internal: "private" } }],
    [{ field: "title", change_type: "modified", new_value: "Title" }],
    [{ ...textChange, change_type: "deleted" }],
  ]) {
    await assert.rejects(
      listPublicJobChanges(
        jobId,
        responseClient(response([{ ...group, changes }])),
      ),
      { code: "INVALID_RESPONSE" },
    );
  }
});

test("salary values preserve exact zero/string bounds, accept unit-only facts, and reject malformed shapes", async () => {
  for (const new_value of [
    null,
    { min: 100, max: null, currency: "USD", period: "year" },
    { min: "NaN", max: null, currency: null, period: null },
    { min: "1.00", max: null, currency: "USD" },
    { min: null, max: null, currency: null, period: null },
  ]) {
    await assert.rejects(
      listPublicJobChanges(
        jobId,
        responseClient(
          response([
            {
              ...group,
              changes: [
                {
                  field: "salary",
                  change_type: "added",
                  old_value: null,
                  new_value,
                },
              ],
            },
          ]),
        ),
      ),
      { code: "INVALID_RESPONSE" },
    );
  }
  const salary = { min: null, max: null, currency: "USD", period: null };
  const result = await listPublicJobChanges(
    jobId,
    responseClient(
      response([
        {
          ...group,
          changes: [
            {
              field: "salary",
              change_type: "added",
              old_value: null,
              new_value: salary,
            },
          ],
        },
      ]),
    ),
  );
  assert.deepEqual(result.items[0].changes[0], {
    field: "salary",
    change_type: "added",
    old_value: null,
    new_value: salary,
  });
});

test("successful empty history stays distinct from missing/failing secondary reads; malformed IDs never fetch", async () => {
  assert.deepEqual(
    await listPublicJobChanges(jobId, responseClient(response([]))),
    response([]),
  );
  for (const status of [404, 500]) {
    await assert.rejects(
      listPublicJobChanges(
        jobId,
        responseClient(
          { error: { code: "PRIVATE_ERROR", message: "private-token" } },
          status,
        ),
      ),
      { status },
    );
  }
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      assert.fail("Malformed IDs must not fetch");
    },
  });
  await assert.rejects(listPublicJobChanges("invalid", client), {
    code: "INVALID_JOB_ID",
  });
});
