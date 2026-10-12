import "server-only";
import { ApiClient, ApiError } from "./client";
import { isRecord, isUuid } from "./validation";

export const SITEMAP_BATCH_SIZE = 1000;
export type PublicSitemapBatch = {
  items: { id: string }[];
  next_after: string | null;
  limit: number;
};

function isItem(value: unknown): value is { id: string } {
  return isRecord(value) && isUuid(value.id);
}

export async function listPublicSitemapJobs(
  after: string | null = null,
  client = new ApiClient(),
): Promise<PublicSitemapBatch> {
  if (after !== null && !isUuid(after)) throw new ApiError(0, "INVALID_CURSOR");
  const params = new URLSearchParams({ limit: String(SITEMAP_BATCH_SIZE) });
  if (after) params.set("after", after);
  const { status, body } = await client.getJson(`/api/v1/public/jobs/sitemap?${params}`);
  if (
    status !== 200 || !isRecord(body) || body.limit !== SITEMAP_BATCH_SIZE ||
    !Array.isArray(body.items) || body.items.length > SITEMAP_BATCH_SIZE ||
    !body.items.every(isItem) || !(body.next_after === null || isUuid(body.next_after))
  ) throw new ApiError(status, "INVALID_RESPONSE");

  const items = body.items.map(({ id }) => ({ id: id.toLowerCase() }));
  const next = body.next_after === null ? null : body.next_after.toLowerCase();
  if (
    items.some((item, index) => item.id <= (index ? items[index - 1].id : after?.toLowerCase() ?? "")) ||
    (next !== null && (items.length !== SITEMAP_BATCH_SIZE || next !== items.at(-1)?.id))
  ) throw new ApiError(status, "INVALID_RESPONSE");

  return { items, next_after: next, limit: body.limit };
}
