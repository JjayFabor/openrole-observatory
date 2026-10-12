import { buildSitemap } from "@/lib/seo/sitemap";
import { getSiteOrigin } from "@/lib/seo/site";

export const dynamic = "force-dynamic";

export default async function sitemap() {
  try {
    return await buildSitemap(getSiteOrigin());
  } catch {
    // A failed walk must not publish partial job entries or private API diagnostics.
    throw new Error("The sitemap is temporarily unavailable.");
  }
}
