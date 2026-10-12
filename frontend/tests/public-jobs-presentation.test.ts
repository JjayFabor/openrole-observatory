import assert from "node:assert/strict";
import test from "node:test";
import {
  getPublicJobSalary,
  getPublicJobTypes,
} from "../lib/public-jobs/presentation";
import { formatAbsoluteTimestamp } from "../lib/dashboard/presentation";
import {
  publicEmploymentOptions,
  publicWorkplaceOptions,
} from "../lib/public-jobs/query-state";
import { publicJob } from "./public-jobs-fixtures";

test("all public filter vocabulary has readable labels and unknown response strings are omitted", () => {
  assert.deepEqual(
    publicWorkplaceOptions.map((workplace_type) =>
      getPublicJobTypes(publicJob({ workplace_type, employment_type: null })),
    ),
    ["Remote", "Hybrid", "On-site"],
  );
  assert.deepEqual(
    publicEmploymentOptions.map((employment_type) =>
      getPublicJobTypes(publicJob({ employment_type, workplace_type: null })),
    ),
    [
      "Full-time",
      "Part-time",
      "Contract",
      "Temporary",
      "Internship",
      "Volunteer",
      "Other",
    ],
  );
  assert.equal(getPublicJobTypes(publicJob()), "Remote · Full-time");
  assert.equal(
    getPublicJobTypes(
      publicJob({
        workplace_type: "future_type",
        employment_type: null,
        location_text: "Remote",
      }),
    ),
    null,
  );
});

test("public salary preserves decimal precision and omits missing currency, period, or bounds", () => {
  assert.equal(getPublicJobSalary(publicJob()), "USD 90,000 – 110,000 / year");
  assert.equal(
    getPublicJobSalary(publicJob({ salary_min: null })),
    "Up to USD 110,000 / year",
  );
  assert.equal(
    getPublicJobSalary(
      publicJob({ salary_min: "9007199254740993.01", salary_max: null }),
    ),
    "USD 9,007,199,254,740,993.01+ / year",
  );
  for (const overrides of [
    { salary_min: null, salary_max: null },
    { salary_currency: null },
    { salary_currency: "XYZ" },
    { salary_period: null },
    { salary_period: "unknown" },
  ]) {
    assert.equal(getPublicJobSalary(publicJob(overrides)), null);
  }
});

test("freshness uses a stable absolute UTC observation timestamp including midnight", () => {
  assert.equal(
    formatAbsoluteTimestamp("2026-10-12T08:00:00+08:00"),
    "Oct 12, 2026, 00:00:00 UTC",
  );
});
