import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { buildApiUrl } from "../lib/api/client";
import { getSiteOrigin } from "../lib/seo/site";

test("production frontend template keeps configuration server-only and indexing explicit", () => {
  const entries = Object.fromEntries(
    readFileSync(".env.production.example", "utf8")
      .split(/\r?\n/)
      .filter((line) => line && !line.startsWith("#"))
      .map((line) => {
        const separator = line.indexOf("=");
        return [line.slice(0, separator), line.slice(separator + 1)];
      }),
  );
  assert.deepEqual(Object.keys(entries).sort(), [
    "NODE_ENV", "OPENROLE_ADMIN_API_TOKEN", "OPENROLE_API_BASE_URL", "OPENROLE_DASHBOARD_PASSWORD", "OPENROLE_DASHBOARD_USERNAME", "OPENROLE_DEFAULT_SOURCE_ID", "OPENROLE_SITE_URL",
  ]);
  assert.equal(entries.NODE_ENV, "production");
  assert.equal(new URL(entries.OPENROLE_API_BASE_URL).protocol, "https:");
  for (const key of ["OPENROLE_ADMIN_API_TOKEN", "OPENROLE_DASHBOARD_USERNAME", "OPENROLE_DASHBOARD_PASSWORD"]) assert.equal(entries[key], "");
  assert.equal(buildApiUrl(entries.OPENROLE_API_BASE_URL, "/api/v1/public/jobs").pathname, "/api/v1/public/jobs");
  assert.equal(entries.OPENROLE_DEFAULT_SOURCE_ID, "");
  assert.equal(entries.OPENROLE_SITE_URL, "");
  assert.equal(getSiteOrigin(entries.OPENROLE_SITE_URL, "production"), null);
  assert.ok(Object.keys(entries).every((key) => !key.startsWith("NEXT_PUBLIC_")));
});
