import type { Metadata, MetadataRoute } from "next";
import { getSiteOrigin, publicPageUrl } from "./site";

type PublicMetadataInput = {
  title: string;
  description: string;
  path: string;
  index: boolean;
  socialTitle?: string;
};

export function buildPublicMetadata(
  input: PublicMetadataInput,
  origin: URL | null = getSiteOrigin(),
): Metadata {
  const url = origin ? publicPageUrl(origin, input.path) : undefined;
  return {
    title: input.title,
    description: input.description,
    alternates: url ? { canonical: url } : undefined,
    robots: { index: Boolean(origin) && input.index, follow: true },
    openGraph: {
      title: input.socialTitle ?? `${input.title} · OpenRole`,
      description: input.description,
      url,
      siteName: "OpenRole",
      type: "website",
    },
  };
}

export function buildHomeMetadata(origin: URL | null = getSiteOrigin()): Metadata {
  return buildPublicMetadata({
    title: "Jobs with visible source freshness",
    socialTitle: "OpenRole — Jobs with visible source freshness",
    description: "OpenRole tracks listings from configured employer ATS sources, recording observations and preserving meaningful changes.",
    path: "/", index: true,
  }, origin);
}

export function buildJobsMetadata(filtered: boolean, origin: URL | null = getSiteOrigin()): Metadata {
  return buildPublicMetadata({
    title: "Jobs",
    description: "Search currently observed listings from configured employer ATS sources with visible last-observed timestamps.",
    path: "/jobs", index: !filtered,
  }, origin);
}

export function buildUnavailableJobMetadata(): Metadata {
  return {
    title: "Job unavailable",
    description: "Job information is temporarily unavailable on OpenRole.",
    robots: { index: false, follow: false },
  };
}

export function buildRobots(origin: URL | null = getSiteOrigin()): MetadataRoute.Robots {
  if (!origin) return { rules: { userAgent: "*", disallow: "/" } };
  return {
    rules: {
      userAgent: "*", allow: "/",
      disallow: ["/dashboard", "/dashboard/", "/api", "/api/"],
    },
    sitemap: publicPageUrl(origin, "/sitemap.xml"),
  };
}
