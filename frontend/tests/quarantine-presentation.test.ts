import assert from "node:assert/strict";
import test from "node:test";
import {
  formatErrorDetails,
  formatQuarantineTimestamp,
  getIdentityPresentation,
  getQuarantineCategoryLabel,
  getQuarantineStatusLabel,
  quarantineCategories,
  truncateErrorMessage,
} from "../lib/quarantine/presentation";

test("category labels reflect five actual writer categories with exact unknown fallback", () => {
  assert.deepEqual(
    quarantineCategories.map((category) => category.value),
    [
      "record_validation_failed",
      "duplicate_source_identifier",
      "normalization_failed",
      "canonicalization_failed",
      "record_domain_validation_failed",
    ],
  );
  assert.equal(
    getQuarantineCategoryLabel("record_validation_failed"),
    "Record validation",
  );
  assert.equal(
    getQuarantineCategoryLabel("schema_validation_failed"),
    "schema_validation_failed",
  );
  assert.equal(getQuarantineCategoryLabel("__proto__"), "__proto__");
});

test("status and nullable timestamps do not invent resolution dates", () => {
  assert.equal(getQuarantineStatusLabel("open"), "Open");
  assert.equal(getQuarantineStatusLabel("resolved"), "Resolved");
  assert.equal(formatQuarantineTimestamp(null), "—");
  assert.equal(
    formatQuarantineTimestamp("2026-10-09T00:00:00Z"),
    "Oct 9, 2026, 00:00:00 UTC",
  );
});

test("identity notes remain conservative and never assert run-level decisions", () => {
  assert.equal(getIdentityPresentation(null).label, "Identity unavailable");
  assert.equal(getIdentityPresentation("0").label, "Identity recoverable");
  assert.match(
    getIdentityPresentation(null).note,
    /can prevent safe absence reconciliation/,
  );
  assert.match(
    getIdentityPresentation("123").note,
    /Run-level safety is determined by the backend/,
  );
  assert.doesNotMatch(
    getIdentityPresentation(null).note,
    /definitely|failed|skipped/,
  );
});

test("message truncation is bounded and keeps full short messages", () => {
  assert.equal(
    truncateErrorMessage("Title is required."),
    "Title is required.",
  );
  assert.equal(Array.from(truncateErrorMessage("🙂".repeat(141))).length, 141);
  assert.ok(truncateErrorMessage("x".repeat(141)).endsWith("…"));
});

test("JSON details are pretty text preserving all nested scalar/array values", () => {
  const details = {
    count: 0,
    valid: false,
    missing: null,
    values: [null, false, 0, { html: "<script>unsafe</script>" }],
  };
  const text = formatErrorDetails(details);
  assert.deepEqual(JSON.parse(text), details);
  assert.match(text, /\n  "count": 0/);
});
