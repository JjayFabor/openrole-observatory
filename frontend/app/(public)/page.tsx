import Link from "next/link";
import { Button } from "@/components/ui/button";
import { buildHomeMetadata } from "@/lib/seo/metadata";

export const metadata = buildHomeMetadata();

export default function PublicHome() {
  return (
    <>
      <section
        aria-labelledby="landing-title"
        className="grid gap-10 py-12 sm:gap-12 sm:py-16 lg:grid-cols-[minmax(0,1fr)_19rem] lg:gap-16 lg:py-20"
      >
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            Direct-source job intelligence
          </p>
          <h1
            id="landing-title"
            className="mt-5 max-w-[16ch] text-4xl font-semibold leading-[1.08] tracking-[-0.045em] sm:text-5xl lg:text-6xl"
          >
            Jobs with visible source freshness.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
            OpenRole tracks listings directly from configured employer ATS
            sources, recording when each listing was last observed and
            preserving meaningful changes.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Button asChild className="h-11 px-5">
              <Link href="/jobs">Browse jobs</Link>
            </Button>
            <Button asChild variant="ghost" className="h-11 px-4">
              <Link href="/#how-it-works">How it works</Link>
            </Button>
          </div>
        </div>
        <section
          aria-labelledby="observed-heading"
          className="self-end border-t border-primary/30 pt-6 lg:mb-1 lg:border-l lg:border-t-0 lg:pl-7 lg:pt-0"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            A note on freshness
          </p>
          <h2
            id="observed-heading"
            className="mt-4 text-2xl font-semibold tracking-tight"
          >
            Observed, explained.
          </h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            “Observed” means OpenRole saw a listing at its employer ATS source.
            The last-observed timestamp records when that evidence was
            collected.
          </p>
          <p className="mt-4 text-sm font-medium leading-6">
            It is source evidence, not confirmation that an employer is hiring.
          </p>
        </section>
      </section>

      <section
        aria-labelledby="principles-heading"
        className="grid gap-7 border-t border-border py-10 sm:py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:gap-16"
      >
        <div>
          <h2
            id="principles-heading"
            className="max-w-xs text-2xl font-semibold leading-tight tracking-tight sm:text-3xl"
          >
            Source evidence.
            <br />
            Useful context.
          </h2>
          <p className="mt-4 max-w-xs text-sm leading-6 text-muted-foreground">
            Current coverage is limited to configured Greenhouse sources. Last
            observed shows when a listing was seen in a source check.
          </p>
        </div>
        <dl className="divide-y divide-border">
          <div className="grid gap-2 pb-5 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-6">
            <dt className="text-sm font-semibold">Direct from employers</dt>
            <dd className="text-sm leading-6 text-muted-foreground">
              Listings come from employer applicant-tracking systems, rather
              than reposted job boards.
            </dd>
          </div>
          <div className="grid gap-2 py-5 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-6">
            <dt className="text-sm font-semibold">Observation timestamps</dt>
            <dd className="text-sm leading-6 text-muted-foreground">
              Last observed tells you when OpenRole saw a listing. It is
              distinct from an employer’s posting or update date.
            </dd>
          </div>
          <div className="grid gap-2 pt-5 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-6">
            <dt className="text-sm font-semibold">Meaningful changes</dt>
            <dd className="text-sm leading-6 text-muted-foreground">
              OpenRole preserves material listing changes, such as title,
              location, or description, to keep their context. Recent listing
              changes are available on public Job Detail.
            </dd>
          </div>
        </dl>
      </section>

      <section
        id="how-it-works"
        aria-labelledby="how-it-works-heading"
        className="scroll-mt-6 border-t border-border py-10 sm:py-12"
      >
        <h2
          id="how-it-works-heading"
          className="text-2xl font-semibold tracking-tight"
        >
          How it works
        </h2>
        <ol className="mt-7 grid gap-6 sm:grid-cols-3 sm:gap-8">
          <li>
            <p className="text-xs font-medium tabular-nums text-primary">01</p>
            <h3 className="mt-2 text-base font-semibold">
              Check a configured source
            </h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              A source check reads the employer’s ATS listings directly.
            </p>
          </li>
          <li>
            <p className="text-xs font-medium tabular-nums text-primary">02</p>
            <h3 className="mt-2 text-base font-semibold">
              Record observations
            </h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Each observed listing keeps a timestamp of that source evidence.
            </p>
          </li>
          <li>
            <p className="text-xs font-medium tabular-nums text-primary">03</p>
            <h3 className="mt-2 text-base font-semibold">
              Preserve material changes
            </h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Changed listing details are retained alongside earlier versions.
            </p>
          </li>
        </ol>
      </section>

      <section
        aria-labelledby="browse-heading"
        className="mb-10 flex flex-col items-start gap-5 border-t border-border pt-8 sm:mb-12 sm:flex-row sm:items-center sm:justify-between sm:gap-8"
      >
        <div>
          <h2
            id="browse-heading"
            className="text-lg font-semibold tracking-tight"
          >
            Find your next listing.
          </h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Browse currently observed listings with source freshness in view.
          </p>
        </div>
        <Button asChild variant="outline" className="h-11 shrink-0 px-5">
          <Link href="/jobs">Browse jobs</Link>
        </Button>
      </section>
    </>
  );
}
