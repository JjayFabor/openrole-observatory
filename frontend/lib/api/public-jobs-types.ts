export type PublicWorkplaceFilter = "remote" | "hybrid" | "onsite";
export type PublicEmploymentFilter =
  | "full_time"
  | "part_time"
  | "contract"
  | "temporary"
  | "internship"
  | "volunteer"
  | "other";

export type PublicJobListItem = {
  id: string;
  title: string;
  company: { name: string; domain: string | null };
  location_text: string | null;
  city: string | null;
  region: string | null;
  country_code: string | null;
  workplace_type: string | null;
  employment_type: string | null;
  salary_min: string | null;
  salary_max: string | null;
  salary_currency: string | null;
  salary_period: string | null;
  first_seen_at: string;
  last_seen_at: string;
  source: { provider: "greenhouse" };
};

export type PublicJobListResponse = {
  items: PublicJobListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PublicJobDetail = PublicJobListItem & {
  company: PublicJobListItem["company"] & { careers_url: string | null };
  lifecycle_status: "observed" | "not_observed";
  description: string | null;
  source_url: string;
  absence_first_detected_at: string | null;
  no_longer_observed_at: string | null;
  reappeared_at: string | null;
};
