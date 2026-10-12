"use client";

import Link from "next/link";
import { useId, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import type { SourceSyncOutcome } from "@/lib/api/types";
import { buildQuarantineHref } from "@/lib/quarantine/query-state";
import {
  getSourceSyncErrorOutcome,
  getSourceSyncPresentation,
} from "@/lib/sources/sync-presentation";

type SyncAction = (sourceId: string) => Promise<SourceSyncOutcome>;

export function SourceSyncFeedback({
  outcome,
}: {
  outcome: SourceSyncOutcome;
}) {
  const presentation = getSourceSyncPresentation(outcome);
  const result = outcome.state === "result" ? outcome.result : undefined;
  return (
    <div className={`rounded-md border p-4 text-sm ${presentation.className}`}>
      <p className="font-medium">{presentation.title}</p>
      <p className="mt-1 break-words text-xs leading-5 [overflow-wrap:anywhere]">
        {presentation.message}
      </p>
      {result && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs">
          <Link
            href={`/dashboard/runs/${result.pipeline_run_id}?source=${result.source_connection_id}`}
            className="underline underline-offset-4 outline-none focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
          >
            View run
          </Link>
          {result.status === "completed_with_errors" && (
            <Link
              href={buildQuarantineHref({
                page: 1,
                source: result.source_connection_id,
                run: result.pipeline_run_id,
              })}
              className="underline underline-offset-4 outline-none focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
            >
              View run quarantine
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

export function SourceSyncButton({
  sourceId,
  active,
  syncAction,
}: {
  sourceId: string;
  active: boolean;
  syncAction: SyncAction;
}) {
  const router = useRouter();
  const explanationId = useId();
  const inFlight = useRef(false);
  const [mutating, setMutating] = useState(false);
  const [refreshing, startRefresh] = useTransition();
  const [outcome, setOutcome] = useState<SourceSyncOutcome>();
  const pending = mutating || refreshing;

  async function handleSync() {
    if (!active || pending || inFlight.current) return;
    inFlight.current = true;
    setMutating(true);
    setOutcome(undefined);
    let nextOutcome: SourceSyncOutcome;
    try {
      nextOutcome = await syncAction(sourceId);
    } catch {
      nextOutcome = getSourceSyncErrorOutcome(0);
    } finally {
      setMutating(false);
      inFlight.current = false;
    }
    setOutcome(nextOutcome);
    if (nextOutcome.state === "result" || nextOutcome.refresh) {
      startRefresh(() => router.refresh());
    }
  }

  return (
    <div className="w-full space-y-3 lg:max-w-md lg:shrink-0">
      <div className="flex flex-col items-start gap-2 lg:items-end">
        <Button
          type="button"
          onClick={handleSync}
          disabled={!active || pending}
          aria-describedby={!active ? explanationId : undefined}
          aria-busy={pending}
        >
          {pending ? "Synchronizing…" : "Sync now"}
        </Button>
        {!active && (
          <p
            id={explanationId}
            className="text-xs leading-5 text-muted-foreground"
          >
            Inactive sources cannot be synchronized.
          </p>
        )}
      </div>
      <div aria-live="polite" aria-atomic="true">
        {pending ? (
          <p className="text-xs leading-5 text-muted-foreground lg:text-right">
            {refreshing
              ? "Refreshing persisted source state…"
              : "Synchronization is running. This may take a few minutes."}
          </p>
        ) : (
          outcome && <SourceSyncFeedback outcome={outcome} />
        )}
      </div>
    </div>
  );
}
