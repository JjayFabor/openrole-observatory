import type { Metadata } from "next";
import type { PublicJobDetail } from "../api/public-jobs-types";
import { formatAbsoluteTimestamp } from "../dashboard/presentation";
import { getPublicJobTypes } from "./presentation";
import { buildPublicMetadata } from "../seo/metadata";
import { getSiteOrigin } from "../seo/site";

function sentence(value: string): string {
  return /[.!?]$/.test(value) ? value : `${value}.`;
}

export function buildPublicJobMetadata(job: PublicJobDetail, origin: URL | null = getSiteOrigin()): Metadata {
  const company = job.company.name.trim();
  const title = `${job.title}${company ? ` at ${company}` : ""}`;
  const types = getPublicJobTypes(job);
  const location = job.location_text?.trim();
  const description = [
    sentence(`${job.lifecycle_status === "not_observed" ? "Historical listing: " : ""}${title}`),
    location ? sentence(location) : null,
    types ? sentence(types) : null,
    `Last observed by OpenRole on ${formatAbsoluteTimestamp(job.last_seen_at)}.`,
  ]
    .filter(Boolean)
    .join(" ");
  return buildPublicMetadata({
    title, description, path: `/jobs/${job.id.toLowerCase()}`,
    index: job.lifecycle_status === "observed" && Boolean(job.title.trim()) && Boolean(company),
  }, origin);
}
