import assert from "node:assert/strict";
import test from "node:test";
import {
  formatPublicChangedSalary,
  formatPublicChangedText,
  formatPublicChangeTimestamp,
  getPublicChangeHeading,
  getPublicChangeValues,
} from "../lib/public-jobs/change-presentation";

test("field/change labels and before/after values are public-facing with no inferred enum or geography", () => {
  assert.equal(
    getPublicChangeHeading({
      field: "workplace_type",
      change_type: "modified",
      old_value: "remote",
      new_value: "hybrid",
    }),
    "Workplace changed",
  );
  assert.deepEqual(
    getPublicChangeValues({
      field: "workplace_type",
      change_type: "modified",
      old_value: "remote",
      new_value: "hybrid",
    }),
    { before: "Remote", after: "Hybrid" },
  );
  assert.equal(
    formatPublicChangedText("employment_type", "full_time"),
    "Full-time",
  );
  assert.equal(
    formatPublicChangedText("workplace_type", "future_value"),
    "Unavailable",
  );
  assert.equal(formatPublicChangedText("workplace_type", null), "Not stated");
  assert.equal(formatPublicChangedText("country_code", "DE"), "DE");
  assert.equal(
    getPublicChangeHeading({
      field: "location_text",
      change_type: "removed",
      old_value: "Berlin",
      new_value: null,
    }),
    "Location removed",
  );
  assert.equal(
    getPublicChangeHeading({ field: "description", change_type: "modified" }),
    "Description updated",
  );
});

test("salary changes keep exact decimals, zero and partial-unit qualification from public detail", () => {
  assert.equal(formatPublicChangedSalary(null), "Not stated");
  assert.equal(
    formatPublicChangedSalary({
      min: "0.00",
      max: null,
      currency: "USD",
      period: "year",
    }),
    "USD 0+ / year",
  );
  assert.equal(
    formatPublicChangedSalary({
      min: "9007199254740993.01",
      max: null,
      currency: null,
      period: "year",
    }),
    "9,007,199,254,740,993.01+ / year (currency unavailable)",
  );
  assert.equal(
    formatPublicChangedSalary({
      min: null,
      max: "123.45",
      currency: "USD",
      period: null,
    }),
    "Up to USD 123.45 (period unavailable)",
  );
});

test("unit-only salary history displays changed facts rather than identical empty amounts", () => {
  const before = { min: null, max: null, currency: "USD", period: "year" };
  const after = { ...before, currency: "EUR", period: "month" };
  assert.deepEqual(
    getPublicChangeValues({
      field: "salary",
      change_type: "modified",
      old_value: before,
      new_value: after,
    }),
    {
      before: "Amount not stated · Currency: USD · Period: year",
      after: "Amount not stated · Currency: EUR · Period: month",
    },
  );
  assert.equal(
    formatPublicChangedSalary({
      min: null,
      max: null,
      currency: "unknown",
      period: "constructor",
    }),
    "Amount not stated · Currency: Unavailable · Period: Unavailable",
  );
});

test("observation dates use deterministic UTC minute precision instead of employer-action timing or seconds", () => {
  assert.equal(
    formatPublicChangeTimestamp("2026-10-12T08:00:31+08:00"),
    "Oct 12, 2026, 00:00 UTC",
  );
});
