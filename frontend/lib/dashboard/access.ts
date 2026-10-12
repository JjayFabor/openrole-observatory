import "server-only";
import { createHash, timingSafeEqual } from "node:crypto";

type AccessEnvironment = {
  NODE_ENV?: string;
  OPENROLE_DASHBOARD_USERNAME?: string;
  OPENROLE_DASHBOARD_PASSWORD?: string;
};

export type DashboardAccess = "allowed" | "unauthorized" | "unconfigured";

function validSetting(value: string | undefined): value is string {
  return (
    typeof value === "string" &&
    Boolean(value.trim()) &&
    !/^(your_|replace_|change_me|changeme)|[<>]/i.test(value)
  );
}

function equals(left: string, right: string): boolean {
  return timingSafeEqual(
    createHash("sha256").update(left).digest(),
    createHash("sha256").update(right).digest(),
  );
}

export function checkDashboardAccess(
  authorization: string | null,
  environment: AccessEnvironment = process.env,
): DashboardAccess {
  const username = environment.OPENROLE_DASHBOARD_USERNAME;
  const password = environment.OPENROLE_DASHBOARD_PASSWORD;
  if (!username && !password && environment.NODE_ENV !== "production") {
    return "allowed";
  }
  if (
    !validSetting(username) ||
    !validSetting(password) ||
    username.includes(":") ||
    password.length < 32
  ) {
    return "unconfigured";
  }
  if (!authorization || authorization.length > 2048) return "unauthorized";
  const match = /^Basic ([A-Za-z0-9+/]+={0,2})$/i.exec(authorization);
  if (!match) return "unauthorized";
  const bytes = Buffer.from(match[1], "base64");
  if (bytes.toString("base64") !== match[1]) return "unauthorized";
  const value = bytes.toString("utf8");
  const colon = value.indexOf(":");
  if (colon < 0) return "unauthorized";
  const sameUsername = equals(value.slice(0, colon), username);
  const samePassword = equals(value.slice(colon + 1), password);
  return sameUsername && samePassword ? "allowed" : "unauthorized";
}

export async function requireDashboardAccess(): Promise<void> {
  // Keep local fixture rendering independent of a Next request context.
  const access = checkDashboardAccess(null);
  if (access === "allowed") return;
  if (access === "unconfigured") throw new Error("Dashboard access denied.");
  const { headers } = await import("next/headers");
  if (checkDashboardAccess((await headers()).get("authorization")) !== "allowed") {
    throw new Error("Dashboard access denied.");
  }
}
