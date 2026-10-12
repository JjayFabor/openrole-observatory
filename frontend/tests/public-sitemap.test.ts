import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient, ApiError } from "../lib/api/client";
import { listPublicSitemapJobs } from "../lib/api/public-sitemap";
import { buildSitemap, MAX_SITEMAP_URLS } from "../lib/seo/sitemap";

const site = new URL("https://openrole.test/");
function uuid(n: number) { return `00000000-0000-4000-8000-${n.toString(16).padStart(12, "0")}`; }
function batchClient(total: number) {
  const requested: number[] = [];
  const client = new ApiClient({ baseUrl: "http://backend.test", fetcher: async (input, options) => {
    const url = new URL(String(input));
    assert.equal(url.pathname, "/api/v1/public/jobs/sitemap");
    assert.equal(url.searchParams.get("limit"), "1000");
    assert.equal(options?.cache, "no-store");
    const after = url.searchParams.get("after");
    const offset = after ? Number.parseInt(after.slice(-12), 16) : 0;
    requested.push(offset);
    const count = Math.min(1000, total - offset);
    const items = Array.from({ length: count }, (_, index) => ({ id: uuid(offset + index + 1), pipeline_run_id: "private" }));
    return Response.json({ items, next_after: offset + count < total ? items.at(-1)!.id : null, limit: 1000, private: "ignored" });
  }});
  return { client, requested };
}

test("sitemap walks every bounded batch, including more than the first discovery page", async () => {
  const { client, requested } = batchClient(2003);
  const entries = await buildSitemap(site, client);
  assert.equal(entries.length, 2005);
  assert.deepEqual(requested, [0, 1000, 2000]);
  assert.deepEqual(entries.slice(0, 2), [{ url: site.href }, { url: "https://openrole.test/jobs" }]);
  assert.equal(entries.at(-1)?.url, `https://openrole.test/jobs/${uuid(2003)}`);
  assert.ok(entries.every(entry => Object.keys(entry).join() === "url"));
  assert.doesNotMatch(JSON.stringify(entries), /dashboard|\/api\/|pipeline_run|private|lastModified|changeFrequency/);
});

test("unset origin emits no fabricated URLs and never contacts the API", async () => {
  const { client, requested } = batchClient(3);
  assert.deepEqual(await buildSitemap(null, client), []);
  assert.deepEqual(requested, []);
});

test("empty eligibility retains only configured public root and Jobs", async () => {
  const { client } = batchClient(0);
  assert.deepEqual(await buildSitemap(site, client), [{ url: site.href }, { url: "https://openrole.test/jobs" }]);
});

test("sitemap boundaries drop extra response fields and reject stalled or invalid cursors", async () => {
  const { client } = batchClient(1001);
  const response = await listPublicSitemapJobs(null, client);
  assert.equal(response.items.length, 1000);
  assert.deepEqual(response.items[0], { id: uuid(1) });
  assert.equal(response.next_after, uuid(1000));
  const invalid = [
    { items: [{ id: "not-uuid" }], next_after: null, limit: 1000 },
    { items: [{ id: uuid(2) }, { id: uuid(1) }], next_after: null, limit: 1000 },
    { items: [{ id: uuid(1) }, { id: uuid(1) }], next_after: null, limit: 1000 },
    { items: [], next_after: uuid(1), limit: 1000 },
    { items: [{ id: uuid(1) }], next_after: null, limit: 25 },
    { items: [], limit: 1000 },
  ];
  for (const body of invalid) {
    const invalidClient = new ApiClient({ baseUrl: "http://backend.test", fetcher: async () => Response.json(body) });
    await assert.rejects(listPublicSitemapJobs(null, invalidClient), ApiError);
  }
  const stalled = new ApiClient({ baseUrl: "http://backend.test", fetcher: async () =>
    Response.json({ items: [{ id: uuid(1000) }], next_after: null, limit: 1000 }) });
  await assert.rejects(listPublicSitemapJobs(uuid(1000), stalled), (error: unknown) => error instanceof ApiError && error.code === "INVALID_RESPONSE");
});

test("sitemap does not return partial entries when a later API batch fails", async () => {
  const { client: first } = batchClient(1001);
  let calls = 0;
  const client = new ApiClient({ baseUrl: "http://backend.test", fetcher: async () => {
    calls += 1;
    if (calls === 1) return Response.json(await listPublicSitemapJobs(null, first));
    return Response.json({ error: { code: "PRIVATE_ERROR", message: "private diagnostics" } }, { status: 500 });
  }});
  await assert.rejects(buildSitemap(site, client), ApiError);
  assert.equal(calls, 2);
});

test("a single sitemap refuses overflow instead of truncating eligible jobs", async () => {
  const { client } = batchClient(MAX_SITEMAP_URLS);
  await assert.rejects(buildSitemap(site, client), (error: unknown) => error instanceof ApiError && error.code === "SITEMAP_TOO_LARGE");
});
