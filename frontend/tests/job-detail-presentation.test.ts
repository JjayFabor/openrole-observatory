import assert from "node:assert/strict";
import test from "node:test";
import {
  formatExactDecimal,
  formatSalary,
  getChangeFieldLabel,
  getChangeTypeLabel,
  getLifecycleEventLabel,
  groupJobChanges,
} from "../lib/jobs/presentation";
import { jobChange } from "./job-detail-fixtures";
test("salary preserves exact decimal precision and never infers currency/period", () => {
  assert.equal(
    formatExactDecimal("9007199254740993123.123456789"),
    "9,007,199,254,740,993,123.123456789",
  );
  assert.equal(formatExactDecimal("65000.00"), "65,000");
  const salary = {
    salary_min: "80000.00",
    salary_max: "100000.00",
    salary_currency: "USD",
    salary_period: "year",
  };
  assert.equal(formatSalary(salary), "USD 80,000 – 100,000 / year");
  assert.equal(
    formatSalary({ ...salary, salary_max: null }),
    "USD 80,000+ / year",
  );
  assert.equal(
    formatSalary({ ...salary, salary_min: null }),
    "Up to USD 100,000 / year",
  );
  assert.equal(
    formatSalary({ ...salary, salary_currency: null, salary_period: null }),
    "80,000 – 100,000",
  );
  assert.equal(
    formatSalary({ ...salary, salary_min: "0.00", salary_max: null }),
    "USD 0+ / year",
  );
  assert.equal(
    formatSalary({ ...salary, salary_min: null, salary_max: null }),
    "—",
  );
});
test("change field/type and lifecycle labels preserve distinct domain concepts", () => {
  assert.equal(getChangeFieldLabel("salary_min"), "Minimum salary");
  assert.equal(getChangeFieldLabel("unknown_field"), "unknown_field");
  assert.equal(getChangeTypeLabel("modified"), "Changed");
  assert.equal(getLifecycleEventLabel("absence_detected"), "Absence detected");
  assert.equal(
    getLifecycleEventLabel("not_observed_confirmed"),
    "Not observed confirmed",
  );
  assert.equal(getLifecycleEventLabel("reappeared"), "Reappeared");
});
test("change grouping preserves persisted records and backend order without recomputing diffs", () => {
  const first = jobChange();
  const second = jobChange({
    id: "99999999-9999-4999-8999-999999999999",
    field_name: "salary_min",
  });
  const third = jobChange({
    from_version_id: first.to_version_id,
    to_version_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    from_version_number: 2,
    to_version_number: 3,
  });
  const groups = groupJobChanges([first, second, third]);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].items, [first, second]);
  assert.deepEqual(groups[1].items, [third]);
});
