import assert from "node:assert/strict";
import test from "node:test";
import { ApiClient, ApiError, buildApiUrl } from "../lib/api/client";

function clientWithResponse(
  body: string,
  status: number,
  contentType = "application/json",
) {
  return new ApiClient({
    baseUrl: "http://backend.test/api/",
    fetcher: async () =>
      new Response(body, { status, headers: { "Content-Type": contentType } }),
  });
}

test("URL construction preserves optional base paths and normalizes trailing slashes", () => {
  assert.equal(
    buildApiUrl("http://localhost:8000", "/health").href,
    "http://localhost:8000/health",
  );
  assert.equal(
    buildApiUrl("https://example.test/openrole///", "/ready").href,
    "https://example.test/openrole/ready",
  );
});

test("URL construction refuses foreign origins, path escapes, credentials and unsupported protocols", () => {
  for (const path of [
    "https://other.test/health",
    "//other.test/health",
    "/../health",
    "/%2e%2e/health",
    "/\\other.test/health",
  ]) {
    assert.throws(() => buildApiUrl("https://example.test/prefix", path), {
      name: "ApiError",
      code: "INVALID_CONFIGURATION",
    });
  }
  for (const base of [
    "file:///tmp",
    "invalid",
    "https://user:password@example.test",
    "https://example.test/?token=secret",
  ]) {
    assert.throws(() => buildApiUrl(base, "/health"), {
      name: "ApiError",
      code: "INVALID_CONFIGURATION",
    });
  }
});

test("requests explicitly avoid caching and include an abort signal", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async (input, init) => {
      assert.equal(String(input), "http://backend.test/health");
      assert.equal(init?.cache, "no-store");
      assert.ok(init?.signal instanceof AbortSignal);
      return Response.json({ status: "ok" });
    },
  });
  assert.deepEqual(await client.getJson("/health"), {
    status: 200,
    body: { status: "ok" },
  });
});

test("structured non-2xx responses preserve status/code without exposing backend messages", async () => {
  const client = clientWithResponse(
    JSON.stringify({
      error: {
        code: "SOURCE_NOT_FOUND",
        message: "Private internals",
        request_id: "id",
      },
    }),
    404,
  );
  await assert.rejects(client.getJson("/health"), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 404);
    assert.equal(error.code, "SOURCE_NOT_FOUND");
    assert.doesNotMatch(error.message, /Private internals/);
    return true;
  });
});

test("unstructured JSON failures remain typed HTTP errors", async () => {
  await assert.rejects(
    clientWithResponse('{"detail":"failure"}', 500).getJson("/health"),
    { name: "ApiError", status: 500 },
  );
});

test("non-JSON error responses preserve their HTTP status", async () => {
  await assert.rejects(
    clientWithResponse("proxy failure", 502, "text/plain").getJson("/health"),
    { name: "ApiError", status: 502 },
  );
});

test("malformed success responses are invalid responses", async () => {
  await assert.rejects(clientWithResponse("not JSON", 200).getJson("/health"), {
    name: "ApiError",
    status: 200,
    code: "INVALID_RESPONSE",
  });
});

test("network failures are typed and sanitized", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      throw new Error("Internal socket detail");
    },
  });
  await assert.rejects(client.getJson("/health"), {
    name: "ApiError",
    status: 0,
    code: "NETWORK_ERROR",
  });
});

test("timeout aborts a pending request", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test",
    timeoutMs: 10,
    fetcher: async (_input, init) => {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    },
  });
  await assert.rejects(client.getJson("/health"), {
    name: "ApiError",
    status: 0,
    code: "TIMEOUT",
  });
});

test("invalid configuration never attempts a network request", async () => {
  const client = new ApiClient({
    baseUrl: "invalid",
    fetcher: async () => {
      assert.fail("Unexpected request");
    },
  });
  await assert.rejects(client.getJson("/health"), {
    name: "ApiError",
    code: "INVALID_CONFIGURATION",
  });
});

test("POST uses an independent mutation timeout while preserving short reads", async () => {
  const client = new ApiClient({
    baseUrl: "http://backend.test/prefix",
    timeoutMs: 5,
    mutationTimeoutMs: 60,
    fetcher: async (input, init) => {
      assert.equal(String(input), "http://backend.test/prefix/sync");
      assert.equal(init?.cache, "no-store");
      return new Promise<Response>((resolve, reject) => {
        const response = setTimeout(
          () => resolve(Response.json({ status: "completed" })),
          20,
        );
        init?.signal?.addEventListener(
          "abort",
          () => {
            clearTimeout(response);
            reject(new DOMException("Aborted", "AbortError"));
          },
          { once: true },
        );
      });
    },
  });
  await assert.rejects(client.getJson("/sync"), { code: "TIMEOUT" });
  assert.deepEqual(await client.postJson("/sync"), {
    status: 200,
    body: { status: "completed" },
  });
});

test("POST aborts once at mutation timeout and sanitizes JSON/HTTP/network failures", async () => {
  let requests = 0;
  const timeout = new ApiClient({
    baseUrl: "http://backend.test",
    mutationTimeoutMs: 5,
    fetcher: async (_input, init) => {
      requests++;
      return new Promise<Response>((_resolve, reject) =>
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        ),
      );
    },
  });
  await assert.rejects(timeout.postJson("/sync"), { code: "TIMEOUT" });
  assert.equal(requests, 1);
  await assert.rejects(clientWithResponse("not-json", 200).postJson("/sync"), {
    code: "INVALID_RESPONSE",
  });
  await assert.rejects(
    clientWithResponse(
      '{"error":{"code":"SOURCE_CONNECTION_INACTIVE","message":"private"}}',
      409,
    ).postJson("/sync"),
    { status: 409, code: "SOURCE_CONNECTION_INACTIVE" },
  );
  const offline = new ApiClient({
    baseUrl: "http://backend.test",
    fetcher: async () => {
      throw new Error("private-socket");
    },
  });
  await assert.rejects(offline.postJson("/sync"), {
    status: 0,
    code: "NETWORK_ERROR",
  });
  await assert.rejects(
    new ApiClient({ baseUrl: "invalid" }).postJson("/sync"),
    { code: "INVALID_CONFIGURATION" },
  );
});
