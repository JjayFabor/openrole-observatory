import { ApiError } from "@/lib/api/client";
import { listPublicJobChanges } from "@/lib/api/public-job-changes";
import type {
  PublicJobChange,
  PublicJobChangesResponse,
} from "@/lib/api/public-job-changes-types";
import {
  formatPublicChangeTimestamp,
  getPublicChangeHeading,
  getPublicChangeValues,
} from "@/lib/public-jobs/change-presentation";
import { Skeleton } from "@/components/ui/skeleton";

function ChangesSection({
  children,
  busy,
}: {
  children: React.ReactNode;
  busy?: boolean;
}) {
  return (
    <section
      aria-labelledby="recent-changes-heading"
      aria-busy={busy}
      className="mt-10 min-w-0 border-t border-border pt-8"
    >
      <h2
        id="recent-changes-heading"
        className="text-xl font-semibold tracking-tight"
      >
        Recent listing changes
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
        Up to 10 recent observations. Dates show when OpenRole saw a changed
        listing, not the exact time of an employer action.
      </p>
      {children}
    </section>
  );
}
function ChangeRow({ change }: { change: PublicJobChange }) {
  if (change.field === "description") {
    return (
      <div className="min-w-0">
        <dt className="text-sm font-medium">
          {getPublicChangeHeading(change)}
        </dt>
        <dd className="sr-only">
          Description content is not included in this history.
        </dd>
      </div>
    );
  }
  const values = getPublicChangeValues(change);
  return (
    <div className="min-w-0">
      <dt className="text-sm font-medium">{getPublicChangeHeading(change)}</dt>
      <dd className="mt-3 min-w-0">
        <dl className="grid min-w-0 gap-3 sm:grid-cols-2 sm:gap-6">
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">Before</dt>
            <dd className="mt-1 text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
              {values.before}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">After</dt>
            <dd className="mt-1 text-sm leading-6 [overflow-wrap:anywhere]">
              {values.after}
            </dd>
          </div>
        </dl>
      </dd>
    </div>
  );
}
export function PublicJobChanges({
  history,
}: {
  history: PublicJobChangesResponse | null;
}) {
  return (
    <ChangesSection>
      {history === null ? (
        <p
          role="status"
          className="mt-6 text-sm leading-6 text-muted-foreground"
        >
          Change history is unavailable right now.
        </p>
      ) : history.items.length === 0 ? (
        <p className="mt-6 text-sm leading-6 text-muted-foreground">
          No material listing changes recorded.
        </p>
      ) : (
        <ol className="mt-6 divide-y divide-border">
          {history.items.map((group, index) => (
            <li
              key={index}
              className="grid min-w-0 gap-5 py-6 first:pt-0 lg:grid-cols-[18rem_minmax(0,1fr)] lg:gap-12"
            >
              <h3 className="text-sm font-medium leading-6 text-muted-foreground">
                <time dateTime={group.observed_at}>
                  {formatPublicChangeTimestamp(group.observed_at)}
                </time>
              </h3>
              <dl className="min-w-0 space-y-6">
                {group.changes.map((change) => (
                  <ChangeRow key={change.field} change={change} />
                ))}
              </dl>
            </li>
          ))}
        </ol>
      )}
    </ChangesSection>
  );
}
export function PublicJobChangesLoading() {
  return (
    <ChangesSection busy>
      <p role="status" className="mt-6 text-sm text-muted-foreground">
        Loading recent changes…
      </p>
      <div aria-hidden="true" className="mt-5 max-w-2xl">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="mt-4 h-4 w-2/3" />
      </div>
    </ChangesSection>
  );
}
export async function PublicJobChangesSection({ jobId }: { jobId: string }) {
  let history: PublicJobChangesResponse | null;
  try {
    history = await listPublicJobChanges(jobId);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    history = null;
  }
  return <PublicJobChanges history={history} />;
}
