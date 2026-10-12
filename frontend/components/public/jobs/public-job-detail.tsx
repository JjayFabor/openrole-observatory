import type { PublicJobDetail as PublicJobDetailData } from "@/lib/api/public-jobs-types";
import { JobDescription } from "@/components/jobs/job-description";
import { Button } from "@/components/ui/button";
import { formatAbsoluteTimestamp } from "@/lib/dashboard/presentation";
import {
  formatWorkplaceType,
  formatEmploymentType,
} from "@/lib/jobs/presentation";
import {
  getSafeCareersUrl,
  getSourceProviderLabel,
} from "@/lib/sources/presentation";
import { getPublicJobTypes } from "@/lib/public-jobs/presentation";
import {
  getPublicDetailSalary,
  getPublicLifecyclePresentation,
} from "@/lib/public-jobs/detail-presentation";

export function PublicJobDetail({ job }: { job: PublicJobDetailData }) {
  const lifecycle = getPublicLifecyclePresentation(job);
  const types = getPublicJobTypes(job);
  const salary = getPublicDetailSalary(job);
  const sourceUrl = getSafeCareersUrl(job.source_url);
  const workplace = formatWorkplaceType(job.workplace_type);
  const employment = formatEmploymentType(job.employment_type);
  return (
    <>
      <header className="grid min-w-0 gap-7 border-b border-border pb-9 lg:grid-cols-[minmax(0,1fr)_19rem] lg:gap-12">
        <div className="min-w-0">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight [overflow-wrap:anywhere] sm:text-4xl">
            {job.title}
          </h1>
          <p className="mt-4 text-lg font-medium [overflow-wrap:anywhere]">
            {job.company.name}
          </p>
          {job.company.domain?.trim() && (
            <p className="mt-1 text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
              {job.company.domain}
            </p>
          )}
          <p className="mt-4 text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
            {job.location_text?.trim()
              ? job.location_text
              : "Location not stated"}
          </p>
          {types && (
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              {types}
            </p>
          )}
          {salary && (
            <p className="mt-3 text-base font-medium leading-7 [overflow-wrap:anywhere]">
              {salary}
            </p>
          )}
        </div>
        <div className="min-w-0 lg:pt-1">
          <p
            className={`text-sm font-semibold ${lifecycle.observed ? "text-primary" : "text-amber-900"}`}
          >
            {lifecycle.label}
          </p>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
            Last observed
          </p>
          <time
            dateTime={job.last_seen_at}
            className="mt-2 block text-sm font-medium leading-6 [overflow-wrap:anywhere]"
          >
            {formatAbsoluteTimestamp(job.last_seen_at)}
          </time>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            Direct source · {getSourceProviderLabel(job.source.provider)}
          </p>
          {sourceUrl && (
            <div className="mt-6">
              <Button
                asChild
                className="h-auto min-h-11 max-w-full whitespace-normal px-5 py-3 text-center"
              >
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-describedby="source-new-tab"
                >
                  {lifecycle.sourceAction}
                </a>
              </Button>
              <p
                id="source-new-tab"
                className="mt-2 text-xs text-muted-foreground"
              >
                Opens in a new tab.
              </p>
            </div>
          )}
        </div>
      </header>

      {!lifecycle.observed && (
        <section
          aria-labelledby="not-observed-heading"
          className="mt-7 border-l-2 border-amber-300 bg-amber-50/60 px-5 py-4"
        >
          <h2 id="not-observed-heading" className="text-base font-semibold">
            This listing is no longer currently observed at its source.
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            This records OpenRole’s observations. It does not establish the
            employer’s current hiring status.
          </p>
          {lifecycle.absenceConfirmedAt && (
            <p className="mt-3 text-sm leading-6">
              Absence confirmed:{" "}
              <time dateTime={lifecycle.absenceConfirmedAt}>
                {formatAbsoluteTimestamp(lifecycle.absenceConfirmedAt)}
              </time>
            </p>
          )}
        </section>
      )}
      {lifecycle.reappearedAt && (
        <p className="mt-6 text-sm leading-6 text-muted-foreground">
          Previously not observed · Reappeared{" "}
          <time dateTime={lifecycle.reappearedAt}>
            {formatAbsoluteTimestamp(lifecycle.reappearedAt)}
          </time>
        </p>
      )}

      <div className="grid min-w-0 gap-10 pt-9 lg:grid-cols-[18rem_minmax(0,1fr)] lg:gap-12">
        <div className="min-w-0">
          <section aria-labelledby="job-details-heading">
            <h2
              id="job-details-heading"
              className="text-lg font-semibold tracking-tight"
            >
              Job details
            </h2>
            <dl className="mt-5 space-y-4 text-sm">
              {workplace !== "—" && (
                <div>
                  <dt className="text-muted-foreground">Workplace</dt>
                  <dd className="mt-1 font-medium">{workplace}</dd>
                </div>
              )}
              {employment !== "—" && (
                <div>
                  <dt className="text-muted-foreground">Employment type</dt>
                  <dd className="mt-1 font-medium">{employment}</dd>
                </div>
              )}
              <div>
                <dt className="text-muted-foreground">First observed</dt>
                <dd className="mt-1 leading-6">
                  <time dateTime={job.first_seen_at}>
                    {formatAbsoluteTimestamp(job.first_seen_at)}
                  </time>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Last observed</dt>
                <dd className="mt-1 leading-6">
                  <time dateTime={job.last_seen_at}>
                    {formatAbsoluteTimestamp(job.last_seen_at)}
                  </time>
                </dd>
              </div>
            </dl>
          </section>
          <section
            aria-labelledby="source-heading"
            className="mt-7 border-t border-border pt-6"
          >
            <h2
              id="source-heading"
              className="text-lg font-semibold tracking-tight"
            >
              Source evidence
            </h2>
            <p className="mt-3 text-sm font-medium">
              Direct source · {getSourceProviderLabel(job.source.provider)}
            </p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              OpenRole observed this listing directly from the employer’s
              applicant-tracking system. The timestamps record when that
              evidence was collected, not confirmation of hiring.
            </p>
          </section>
        </div>
        <section
          aria-labelledby="description-heading"
          className="min-w-0 border-t border-border pt-7 lg:border-t-0 lg:pt-0"
        >
          <h2
            id="description-heading"
            className="text-xl font-semibold tracking-tight"
          >
            Description
          </h2>
          <div className="mt-5 min-w-0">
            <JobDescription
              description={job.description}
              emptyText="No description is available for this listing."
              className="text-base leading-8"
            />
          </div>
        </section>
      </div>
    </>
  );
}
