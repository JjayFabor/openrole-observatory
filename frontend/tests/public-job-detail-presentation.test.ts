import assert from "node:assert/strict";
import test from "node:test";
import {
  getPublicDetailSalary,
  getPublicLifecyclePresentation,
} from "../lib/public-jobs/detail-presentation";
import { buildPublicJobMetadata } from "../lib/public-jobs/detail-metadata";
import { getPublicJobSalary } from "../lib/public-jobs/presentation";
import { publicJobDetail } from "./public-jobs-fixtures";

test("current lifecycle controls source wording while tentative absence remains observed", () => {
  const observed = getPublicLifecyclePresentation(
    publicJobDetail({ absence_first_detected_at: "2026-10-10T00:00:00Z" }),
  );
  assert.equal(observed.label, "Observed");
  assert.equal(observed.sourceAction, "View original listing");
  assert.equal(observed.absenceConfirmedAt, null);
  const absent = getPublicLifecyclePresentation(
    publicJobDetail({
      lifecycle_status: "not_observed",
      no_longer_observed_at: "2026-10-11T00:00:00Z",
    }),
  );
  assert.equal(absent.label, "Not currently observed");
  assert.equal(absent.sourceAction, "Check original source");
  assert.equal(absent.absenceConfirmedAt, "2026-10-11T00:00:00Z");
});

test("reappearance is secondary context and old confirmation is not a current absence warning", () => {
  const state = getPublicLifecyclePresentation(
    publicJobDetail({
      reappeared_at: "2026-10-12T00:00:00Z",
      no_longer_observed_at: "2026-10-11T00:00:00Z",
    }),
  );
  assert.equal(state.label, "Observed");
  assert.equal(state.reappearedAt, "2026-10-12T00:00:00Z");
  assert.equal(state.absenceConfirmedAt, null);
  assert.equal(
    getPublicLifecyclePresentation(
      publicJobDetail({
        lifecycle_status: "not_observed",
        reappeared_at: state.reappearedAt,
      }),
    ).reappearedAt,
    null,
  );
});

test("detail salary preserves partial amounts and zero while explicitly qualifying unknown units", () => {
  assert.equal(
    getPublicDetailSalary(publicJobDetail()),
    "USD 90,000 – 110,000 / year",
  );
  assert.equal(
    getPublicDetailSalary(publicJobDetail({ salary_min: null })),
    "Up to USD 110,000 / year",
  );
  assert.equal(
    getPublicDetailSalary(
      publicJobDetail({
        salary_min: "0.00",
        salary_max: null,
        salary_currency: null,
      }),
    ),
    "0+ / year (currency unavailable)",
  );
  assert.equal(
    getPublicDetailSalary(
      publicJobDetail({
        salary_min: "9007199254740993.01",
        salary_max: null,
        salary_period: null,
      }),
    ),
    "USD 9,007,199,254,740,993.01+ (period unavailable)",
  );
  const incomplete = publicJobDetail({
    salary_min: "123.45",
    salary_max: null,
    salary_currency: "XYZ",
    salary_period: "constructor",
  });
  assert.equal(
    getPublicDetailSalary(incomplete),
    "123.45+ (currency unavailable; period unavailable)",
  );
  assert.equal(getPublicJobSalary(incomplete), null);
  assert.equal(
    getPublicDetailSalary(
      publicJobDetail({ salary_min: null, salary_max: null }),
    ),
    null,
  );
});

test("metadata uses real title/company, known optional fields and observation date without invented public data", () => {
  const metadata = buildPublicJobMetadata(publicJobDetail(), null);
  assert.equal(metadata.title, "Backend Engineer at Example Employer");
  assert.match(
    metadata.description ?? "",
    /Berlin.*Remote · Full-time.*Last observed.*UTC/,
  );
  assert.equal(metadata.alternates, undefined);
  assert.equal(metadata.openGraph?.title, "Backend Engineer at Example Employer · OpenRole");
  assert.equal(metadata.openGraph?.url, undefined);
  assert.deepEqual(metadata.robots, { index: false, follow: true });
  const sparse = buildPublicJobMetadata(
    publicJobDetail({
      company: { name: "", domain: null, careers_url: null },
      location_text: null,
      workplace_type: "future_type",
      employment_type: null,
    }),
  );
  assert.equal(sparse.title, "Backend Engineer");
  assert.doesNotMatch(
    sparse.description ?? "",
    /null|undefined|future_type|Location not stated|—/,
  );
  const historical = buildPublicJobMetadata(
    publicJobDetail({ lifecycle_status: "not_observed" }),
  );
  assert.match(historical.description ?? "", /Historical listing/);
  assert.doesNotMatch(
    JSON.stringify(historical),
    /Closed|Expired|Posted|actively hiring|description_html/i,
  );
});
