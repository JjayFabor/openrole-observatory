/** An explicit origin prevents a deployment hostname from becoming canonical. */
export function getSiteOrigin(
  value = process.env.OPENROLE_SITE_URL,
  environment = process.env.NODE_ENV ?? "production",
): URL | null {
  if (!value?.trim()) return null;
  try {
    const url = new URL(value.trim());
    if (
      !["http:", "https:"].includes(url.protocol) || url.username || url.password ||
      url.pathname !== "/" || url.search || url.hash
    ) return null;
    const host = url.hostname.replace(/^\[|\]$/g, "").toLowerCase();
    if (!host.includes(":") && !/^[a-z0-9.-]+$/.test(host)) return null;
    const local = host === "localhost" || host.endsWith(".localhost") ||
      host === "::1" || host === "0.0.0.0" || host.startsWith("127.");
    if (environment === "production" && (url.protocol !== "https:" || local)) return null;
    return new URL(url.origin);
  } catch {
    return null;
  }
}

export function publicPageUrl(origin: URL, path: string): string {
  return new URL(path, origin).href;
}
