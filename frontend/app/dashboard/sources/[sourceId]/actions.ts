"use server";

import { revalidatePath } from "next/cache";
import { ApiError } from "@/lib/api/client";
import { syncSource } from "@/lib/api/source-sync";
import type { SourceSyncOutcome } from "@/lib/api/types";
import { isUuid } from "@/lib/api/validation";
import { getSourceSyncErrorOutcome } from "@/lib/sources/sync-presentation";

export async function synchronizeSource(
  sourceId: string,
): Promise<SourceSyncOutcome> {
  let outcome: SourceSyncOutcome;
  try {
    outcome = { state: "result", result: await syncSource(sourceId) };
  } catch (error) {
    outcome =
      error instanceof ApiError
        ? getSourceSyncErrorOutcome(error.status, error.code)
        : getSourceSyncErrorOutcome(0);
  }
  // A lost response leaves the result unknown; retain the mounted source and feedback.
  if (outcome.state === "result" || outcome.refresh) {
    if (isUuid(sourceId)) revalidatePath(`/dashboard/sources/${sourceId}`);
    for (const path of [
      "/dashboard/sources",
      "/dashboard",
      "/dashboard/jobs",
      "/dashboard/quarantine",
      "/dashboard/runs",
    ]) {
      revalidatePath(path);
    }
  }
  return outcome;
}
