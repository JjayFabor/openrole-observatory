import assert from "node:assert/strict";
import test from "node:test";
import {
  dashboardSections,
  getDashboardSection,
} from "../lib/dashboard/navigation";
test("header/sidebar share nested section matching without prefix collisions", () => {
  for (const section of dashboardSections)
    assert.equal(getDashboardSection(section.href)?.label, section.label);
  for (const [path, label] of [
    ["/dashboard/jobs/UUID", "Jobs"],
    ["/dashboard/runs/UUID", "Pipeline Runs"],
    ["/dashboard/sources/UUID", "Sources"],
    ["/dashboard/quarantine/UUID", "Quarantine"],
  ])
    assert.equal(getDashboardSection(path)?.label, label);
  for (const path of [
    "/dashboard/jobseeker",
    "/dashboard/runsExtra",
    "/dashboardish",
    "/dashboard/unknown",
  ])
    assert.equal(getDashboardSection(path), undefined);
});
