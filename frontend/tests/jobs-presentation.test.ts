import assert from "node:assert/strict";
import test from "node:test";
import {
  formatEmploymentType,
  formatWorkplaceType,
  getLifecycleLabel,
} from "../lib/jobs/presentation";

test("lifecycle labels retain observational terminology", () => {
  assert.equal(getLifecycleLabel("observed"), "Observed");
  assert.equal(getLifecycleLabel("not_observed"), "Not observed");
});

test("canonical types are humanized without inferring missing data", () => {
  assert.equal(formatWorkplaceType("onsite"), "On-site");
  assert.equal(formatWorkplaceType("remote"), "Remote");
  assert.equal(formatWorkplaceType("hybrid"), "Hybrid");
  assert.equal(formatEmploymentType("full_time"), "Full-time");
  assert.equal(formatEmploymentType("part_time"), "Part-time");
  assert.equal(formatEmploymentType("contract"), "Contract");
  for (const unknown of [
    null,
    "",
    "unknown",
    "__proto__",
    "constructor",
    "toString",
  ]) {
    assert.equal(formatWorkplaceType(unknown), "—");
    assert.equal(formatEmploymentType(unknown), "—");
  }
});
