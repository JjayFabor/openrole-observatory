import type {
  PublicJobDetail,
  PublicJobListItem,
} from "../lib/api/public-jobs-types";

export function publicJob(
  overrides: Partial<PublicJobListItem> = {},
): PublicJobListItem {
  return {
    id: "33333333-3333-4333-8333-333333333333",
    title: "Backend Engineer",
    company: { name: "Example Employer", domain: "example.test" },
    location_text: "Berlin",
    city: null,
    region: null,
    country_code: null,
    workplace_type: "remote",
    employment_type: "full_time",
    salary_min: "90000.00",
    salary_max: "110000.00",
    salary_currency: "USD",
    salary_period: "year",
    first_seen_at: "2026-10-01T10:00:00Z",
    last_seen_at: "2026-10-12T00:00:00Z",
    source: { provider: "greenhouse" },
    ...overrides,
  };
}

export function publicJobDetail(
  overrides: Partial<PublicJobDetail> = {},
): PublicJobDetail {
  return {
    ...publicJob(),
    company: {
      name: "Example Employer",
      domain: "example.test",
      careers_url: "https://example.test/careers",
    },
    description: "<p>Build reliable systems.</p>",
    source_url: "https://boards.greenhouse.io/example/jobs/123",
    lifecycle_status: "observed",
    absence_first_detected_at: null,
    no_longer_observed_at: null,
    reappeared_at: null,
    ...overrides,
  };
}
