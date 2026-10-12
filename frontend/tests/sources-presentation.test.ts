import assert from "node:assert/strict";
import test from "node:test";
import {
  formatSourceTimestamp,
  getSafeCareersUrl,
  getSourceActiveLabel,
  getSourceProviderLabel,
  isNeverSynchronized,
} from "../lib/sources/presentation";

test("source configuration labels remain separate from pipeline status", () => {
  assert.equal(getSourceActiveLabel(true), "Active");
  assert.equal(getSourceActiveLabel(false), "Inactive");
  assert.equal(getSourceProviderLabel("greenhouse"), "Greenhouse");
});

test("never synchronized requires both facts null and nullable dates display a dash", () => {
  assert.equal(
    isNeverSynchronized({
      last_attempted_sync_at: null,
      last_successful_sync_at: null,
    }),
    true,
  );
  assert.equal(
    isNeverSynchronized({
      last_attempted_sync_at: "2026-10-09T10:00:00Z",
      last_successful_sync_at: null,
    }),
    false,
  );
  assert.equal(formatSourceTimestamp(null), "—");
  assert.equal(
    formatSourceTimestamp("2026-10-09T00:00:00Z"),
    "Oct 9, 2026, 00:00:00 UTC",
  );
});

test("careers links accept only valid credential-free HTTP(S) URLs", () => {
  assert.equal(
    getSafeCareersUrl("https://example.test/careers"),
    "https://example.test/careers",
  );
  assert.equal(
    getSafeCareersUrl("http://example.test"),
    "http://example.test/",
  );
  for (const value of [
    null,
    "",
    "javascript:alert(1)",
    "data:text/html,<script>unsafe</script>",
    "ftp://example.test",
    "//example.test",
    "invalid",
    "https://user:secret@example.test/",
  ])
    assert.equal(getSafeCareersUrl(value), null);
});
