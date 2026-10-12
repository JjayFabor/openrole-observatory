import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { getJobDetail } from "../lib/api/job-detail";
import {
  jobChange,
  jobId,
  jobLifecycle,
  jobRead,
  jobVersion,
} from "./job-detail-fixtures";
import { sourceRead } from "./source-fixtures";
const query = { versions: 1, changes: 1, lifecycle: 1 };
function client(failures: string[] = [], primaryStatus = 200) {
  const paths: string[] = [];
  return {
    paths,
    api: new ApiClient({
      baseUrl: "http://backend.test",
      fetcher: async (input) => {
        const url = new URL(String(input));
        paths.push(url.pathname);
        if (failures.some((value) => url.pathname.endsWith(value)))
          throw new Error("private-token-internal-sql");
        if (url.pathname.endsWith(jobId))
          return Response.json(
            primaryStatus === 200
              ? jobRead()
              : { error: { code: "JOB_NOT_FOUND" } },
            { status: primaryStatus },
          );
        if (url.pathname.includes("sources"))
          return Response.json(sourceRead());
        assert.equal(url.searchParams.get("limit"), "26");
        assert.equal(url.searchParams.get("offset"), "0");
        if (url.pathname.endsWith("versions"))
          return Response.json({ items: [jobVersion()], limit: 26, offset: 0 });
        if (url.pathname.endsWith("changes"))
          return Response.json({ items: [jobChange()], limit: 26, offset: 0 });
        return Response.json(jobLifecycle());
      },
    }),
  };
}
test("job primary precedes independent source and history reads", async () => {
  const { api, paths } = client();
  const detail = await getJobDetail(jobId, query, api);
  assert.equal(detail.state, "available");
  if (detail.state !== "available") assert.fail("Missing primary");
  for (const key of ["source", "versions", "changes", "lifecycle"] as const)
    assert.equal(detail[key].state, "available");
  assert.equal(paths[0], `/api/v1/jobs/${jobId}`);
  assert.equal(paths.length, 5);
});
test("all secondary error combinations leave current content and other histories intact", async () => {
  for (let mask = 0; mask < 16; mask++) {
    const paths = [sourceRead().id, "versions", "changes", "lifecycle"].filter(
      (_path, index) => mask & (1 << index),
    );
    const detail = await getJobDetail(jobId, query, client(paths).api);
    assert.equal(detail.state, "available");
    if (detail.state !== "available") assert.fail("Missing primary");
    assert.equal(detail.job.current_version.title, "Backend Engineer");
    (["source", "versions", "changes", "lifecycle"] as const).forEach(
      (key, index) =>
        assert.equal(
          detail[key].state,
          mask & (1 << index) ? "unavailable" : "available",
        ),
    );
    assert.doesNotMatch(JSON.stringify(detail), /private-token/);
  }
});
test("primary404/error/invalidUUID stops dependent requests", async () => {
  for (const [status, state] of [
    [404, "not_found"],
    [500, "unavailable"],
  ] as const) {
    const { api, paths } = client([], status);
    assert.deepEqual(await getJobDetail(jobId, query, api), { state });
    assert.equal(paths.length, 1);
  }
  const { api, paths } = client();
  assert.deepEqual(await getJobDetail("invalid", query, api), {
    state: "not_found",
  });
  assert.equal(paths.length, 0);
});
test("secondary reads are concurrent after primary resolution", async () => {
  const releases: (() => void)[] = [];
  let signal: (() => void) | undefined;
  const started = new Promise<void>((resolve) => {
    signal = resolve;
  });
  const api = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) => {
      const path = new URL(String(input)).pathname;
      if (path.endsWith(jobId)) return Response.json(jobRead());
      await new Promise<void>((resolve) => {
        releases.push(resolve);
        if (releases.length === 4) signal?.();
      });
      if (path.includes("sources")) return Response.json(sourceRead());
      if (path.endsWith("lifecycle")) return Response.json(jobLifecycle());
      return Response.json({ items: [], limit: 26, offset: 0 });
    },
  });
  const pending = getJobDetail(jobId, query, api);
  await started;
  assert.equal(releases.length, 4);
  releases.forEach((release) => release());
  assert.equal((await pending).state, "available");
});
