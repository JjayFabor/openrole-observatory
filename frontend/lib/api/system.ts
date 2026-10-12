import "server-only";

import { ApiClient, ApiError } from "./client";
import type { HealthResponse, ReadinessResponse, SystemStatus } from "./types";
import { isRecord } from "./validation";

export async function getHealth(
  client = new ApiClient(),
): Promise<HealthResponse> {
  const { status, body } = await client.getJson("/health");
  if (status !== 200 || !isRecord(body) || body.status !== "ok") {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  return { status: "ok" };
}

export async function getReadiness(
  client = new ApiClient(),
): Promise<ReadinessResponse> {
  // /ready deliberately returns a meaningful database status with HTTP 503.
  const { status, body } = await client.getJson("/ready", [503]);
  if (isRecord(body)) {
    if (
      status === 200 &&
      body.status === "ready" &&
      body.database === "available"
    ) {
      return { status: "ready", database: "available" };
    }
    if (
      status === 503 &&
      body.status === "not_ready" &&
      body.database === "unavailable"
    ) {
      return { status: "not_ready", database: "unavailable" };
    }
  }
  throw new ApiError(status, "INVALID_RESPONSE");
}

export async function getSystemStatus(
  client = new ApiClient(),
): Promise<SystemStatus> {
  const [health, readiness] = await Promise.allSettled([
    getHealth(client),
    getReadiness(client),
  ]);
  return {
    api: health.status === "fulfilled" ? "healthy" : "unavailable",
    database:
      readiness.status === "fulfilled" ? readiness.value.status : "unavailable",
  };
}
