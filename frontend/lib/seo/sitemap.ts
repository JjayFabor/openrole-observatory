import "server-only";
import type { MetadataRoute } from "next";
import { ApiClient, ApiError } from "../api/client";
import { listPublicSitemapJobs } from "../api/public-sitemap";
import { publicPageUrl } from "./site";

export const MAX_SITEMAP_URLS = 50_000;

export async function buildSitemap(
  origin: URL | null,
  client = new ApiClient(),
): Promise<MetadataRoute.Sitemap> {
  if (!origin) return [];
  const entries: MetadataRoute.Sitemap = [
    { url: publicPageUrl(origin, "/") },
    { url: publicPageUrl(origin, "/jobs") },
  ];
  let after: string | null = null;
  do {
    const batch = await listPublicSitemapJobs(after, client);
    for (const item of batch.items) {
      entries.push({ url: publicPageUrl(origin, `/jobs/${item.id}`) });
    }
    // Do not publish a silently truncated sitemap once one file is insufficient.
    if (entries.length > MAX_SITEMAP_URLS) throw new ApiError(0, "SITEMAP_TOO_LARGE");
    after = batch.next_after;
  } while (after !== null);
  return entries;
}
