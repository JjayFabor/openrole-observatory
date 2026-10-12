import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient } from "../lib/api/client";
import { getHealth, getReadiness, getSystemStatus } from "../lib/api/system";

function responseClient(body: unknown, status = 200) {
  return new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => Response.json(body, { status }),
  });
}

test("health accepts the actual backend contract", async () => {
  assert.deepEqual(await getHealth(responseClient({ status: "ok" })), {
    status: "ok",
  });
});

test("health rejects payloads that do not match the backend contract", async () => {
  for (const payload of [null, [], { status: "healthy" }, { healthy: true }]) {
    await assert.rejects(getHealth(responseClient(payload)), {
      code: "INVALID_RESPONSE",
    });
  }
});

test("readiness accepts both ready and confirmed database-unavailable responses", async () => {
  assert.deepEqual(
    await getReadiness(
      responseClient({ status: "ready", database: "available" }),
    ),
    { status: "ready", database: "available" },
  );
  assert.deepEqual(
    await getReadiness(
      responseClient({ status: "not_ready", database: "unavailable" }, 503),
    ),
    { status: "not_ready", database: "unavailable" },
  );
});

test("readiness validates fields together with their HTTP status", async () => {
  for (const [payload, status] of [
    [{ status: "ready", database: "unavailable" }, 200],
    [{ status: "ready", database: "available" }, 503],
    [{ status: "not_ready", database: "unavailable" }, 200],
    [{ error: { code: "PROXY_ERROR" } }, 503],
    [null, 200],
  ] as const) {
    await assert.rejects(getReadiness(responseClient(payload, status)), {
      code: "INVALID_RESPONSE",
    });
  }
});

test("system status maps successful checks independently", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) =>
      Response.json(
        String(input).endsWith("/health")
          ? { status: "ok" }
          : { status: "ready", database: "available" },
      ),
  });
  assert.deepEqual(await getSystemStatus(client), {
    api: "healthy",
    database: "ready",
  });
});

test("confirmed database failure preserves API health", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) =>
      String(input).endsWith("/health")
        ? Response.json({ status: "ok" })
        : Response.json(
            { status: "not_ready", database: "unavailable" },
            { status: 503 },
          ),
  });
  assert.deepEqual(await getSystemStatus(client), {
    api: "healthy",
    database: "not_ready",
  });
});

test("failed readiness checks do not infer database failure or suppress healthy API", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) => {
      if (String(input).endsWith("/health"))
        return Response.json({ status: "ok" });
      throw new Error("Network failure");
    },
  });
  assert.deepEqual(await getSystemStatus(client), {
    api: "healthy",
    database: "unavailable",
  });
});

test("failed health check does not suppress successful readiness", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input) =>
      String(input).endsWith("/health")
        ? Response.json({ status: "invalid" })
        : Response.json({ status: "ready", database: "available" }),
  });
  assert.deepEqual(await getSystemStatus(client), {
    api: "unavailable",
    database: "ready",
  });
});

test("backend outage returns unavailable checks without crashing the page", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      throw new Error("Backend stopped");
    },
  });
  assert.deepEqual(await getSystemStatus(client), {
    api: "unavailable",
    database: "unavailable",
  });
});

test("invalid environment configuration leaves status checks unavailable", async () => {
  assert.deepEqual(await getSystemStatus(new ApiClient({ baseUrl: "" })), {
    api: "unavailable",
    database: "unavailable",
  });
});
