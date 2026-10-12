import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { NextRequest } from "next/server";
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { checkDashboardAccess } from "../lib/dashboard/access";
import { ApiClient } from "../lib/api/client";
import { config, proxy } from "../proxy";
import { synchronizeSource } from "../app/dashboard/sources/[sourceId]/actions";

function setEnvironment(t: TestContext, key: string, value: string): void {
  const previous = process.env[key];
  process.env[key] = value;
  t.after(() => {
    if (previous === undefined) delete process.env[key];
    else process.env[key] = previous;
  });
}

const credentials = {
  NODE_ENV: "production",
  OPENROLE_DASHBOARD_USERNAME: "operator",
  OPENROLE_DASHBOARD_PASSWORD: "synthetic-dashboard-password-32-characters",
};
function basic(username = credentials.OPENROLE_DASHBOARD_USERNAME, password = credentials.OPENROLE_DASHBOARD_PASSWORD) {
  return `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
}

test("production fails closed while unconfigured local development remains accessible", () => {
  assert.equal(checkDashboardAccess(null, { NODE_ENV: "production" }), "unconfigured");
  assert.equal(checkDashboardAccess(null, { NODE_ENV: "development" }), "allowed");
  for (const override of [
    { OPENROLE_DASHBOARD_PASSWORD: "" },
    { OPENROLE_DASHBOARD_PASSWORD: "short" },
    { OPENROLE_DASHBOARD_PASSWORD: "REPLACE_ME".repeat(4) },
    { OPENROLE_DASHBOARD_USERNAME: "user:name" },
    { OPENROLE_DASHBOARD_USERNAME: " " },
  ]) assert.equal(checkDashboardAccess(basic(), { ...credentials, ...override }), "unconfigured");
});

test("dashboard credentials are required and malformed or incorrect values never authenticate", () => {
  assert.equal(checkDashboardAccess(basic(), credentials), "allowed");
  assert.equal(checkDashboardAccess(basic().replace("Basic", "basic"), credentials), "allowed");
  for (const authorization of [null, "Bearer token", "Basic !invalid!", "Basic YQ==", "Basic YQ=", "Basic " + "a".repeat(3000), basic("wrong"), basic("operator", "wrong")]) {
    assert.equal(checkDashboardAccess(authorization, credentials), "unauthorized");
  }
});

test("proxy matcher covers dashboard pages, data requests and action POST destinations only", () => {
  for (const url of ["/dashboard", "/dashboard/jobs", "/dashboard/sources/11111111-1111-4111-8111-111111111111", "/dashboard/runs?source=example"]) {
    assert.equal(unstable_doesMiddlewareMatch({ config, nextConfig: {}, url }), true);
  }
  for (const url of ["/", "/jobs", "/jobs/example", "/robots.txt", "/sitemap.xml", "/_next/static/example.js", "/dashboard-other"]) {
    assert.equal(unstable_doesMiddlewareMatch({ config, nextConfig: {}, url }), false);
    assert.equal(unstable_doesMiddlewareMatch({ config, nextConfig: {}, url, headers: { "next-action": "sync-action" } }), true);
  }
});

test("proxy rejects page and action requests, ignores spoofed bypass headers and permits valid credentials", (t) => {
  setEnvironment(t, "NODE_ENV", "production");
  setEnvironment(t, "OPENROLE_DASHBOARD_USERNAME", credentials.OPENROLE_DASHBOARD_USERNAME);
  setEnvironment(t, "OPENROLE_DASHBOARD_PASSWORD", credentials.OPENROLE_DASHBOARD_PASSWORD);
  for (const method of ["GET", "POST"]) {
    const rejected = proxy(new NextRequest("https://frontend.test/dashboard/sources/example", {
      method, headers: { "x-middleware-subrequest": "proxy", "next-action": "invented-action" },
    }));
    assert.equal(rejected.status, 401);
    assert.match(rejected.headers.get("www-authenticate")!, /^Basic /);
    assert.match(rejected.headers.get("cache-control")!, /no-store/);
  }
  assert.equal(proxy(new NextRequest("https://frontend.test/dashboard", { headers: { Authorization: basic() } })).status, 200);
  process.env.OPENROLE_DASHBOARD_PASSWORD = "";
  assert.equal(proxy(new NextRequest("https://frontend.test/dashboard")).status, 503);
});

test("API token is attached only to administrative requests and is never forwarded to public or health reads", async (t) => {
  setEnvironment(t, "NODE_ENV", "development");
  setEnvironment(t, "OPENROLE_DASHBOARD_USERNAME", "");
  setEnvironment(t, "OPENROLE_DASHBOARD_PASSWORD", "");
  setEnvironment(t, "OPENROLE_ADMIN_API_TOKEN", "synthetic-administrative-token-32-characters");
  const requests: { pathname: string; authorization: string | null }[] = [];
  const client = new ApiClient({ baseUrl: "https://backend.test/prefix", fetcher: async (input, init) => {
    requests.push({ pathname: new URL(String(input)).pathname, authorization: new Headers(init?.headers).get("authorization") });
    return Response.json({});
  } });
  await client.getJson("/api/v1/sources");
  await client.postJson("/api/v1/sources/example/sync");
  await client.getJson("/api/v1/public/../sources");
  for (const path of ["/api/v1/public/jobs", "/api/v1/public/jobs/example/changes", "/health", "/ready"]) await client.getJson(path);
  assert.ok(requests.slice(0, 3).every(({ authorization }) => authorization === "Bearer synthetic-administrative-token-32-characters"));
  assert.ok(requests.slice(3).every(({ authorization }) => authorization === null));
});

test("administrative API reads cannot use the backend token without dashboard authorization", async (t) => {
  setEnvironment(t, "NODE_ENV", "production");
  setEnvironment(t, "OPENROLE_DASHBOARD_USERNAME", "");
  setEnvironment(t, "OPENROLE_DASHBOARD_PASSWORD", "");
  setEnvironment(t, "OPENROLE_ADMIN_API_TOKEN", "synthetic-administrative-token-32-characters");
  let fetched = false;
  const client = new ApiClient({ baseUrl: "https://backend.test", fetcher: async () => { fetched = true; return Response.json({}); } });
  await assert.rejects(client.getJson("/api/v1/sources"));
  assert.equal(fetched, false);
  await client.getJson("/api/v1/public/jobs");
  assert.equal(fetched, true);
});

test("the manual sync Server Action refuses anonymous invocation before fetching or refreshing", async (t) => {
  setEnvironment(t, "NODE_ENV", "production");
  setEnvironment(t, "OPENROLE_DASHBOARD_USERNAME", "");
  setEnvironment(t, "OPENROLE_DASHBOARD_PASSWORD", "");
  let fetched = false;
  t.mock.method(globalThis, "fetch", async () => { fetched = true; return Response.json({}); });
  await assert.rejects(synchronizeSource("11111111-1111-4111-8111-111111111111"), /Dashboard access denied/);
  assert.equal(fetched, false);
});
