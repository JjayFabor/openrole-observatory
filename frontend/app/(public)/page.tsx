import Link from "next/link";
import { Button } from "@/components/ui/button";
import { buildHomeMetadata } from "@/lib/seo/metadata";

export const metadata = buildHomeMetadata();

export default function PublicHome() {
  return (
    <>
      <section
        aria-labelledby="landing-title"
        className="grid gap-10 py-12 sm:gap-12 sm:py-16 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-center lg:gap-[clamp(2rem,4vw,6rem)] lg:py-20 xl:py-24"
      >
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary xl:text-sm">
            Direct-source job intelligence
          </p>
          <h1
            id="landing-title"
            className="mt-5 max-w-[16ch] text-[clamp(2.5rem,4.5vw,5.5rem)] font-semibold leading-[1.08] tracking-[-0.045em]"
          >
            Jobs with visible source freshness.
          </h1>
          <p className="mt-6 max-w-[52ch] text-base leading-relaxed text-muted-foreground sm:text-lg xl:mt-8 xl:text-xl 2xl:text-[1.375rem]">
            OpenRole tracks listings directly from configured employer ATS
            sources, recording when each listing was last observed and
            preserving meaningful changes.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3 sm:gap-4 xl:mt-10">
            <Button asChild className="h-12 px-6 text-base xl:h-14 xl:px-7">
              <Link href="/jobs">Browse jobs</Link>
            </Button>
            <Button asChild variant="ghost" className="h-12 px-5 text-base xl:h-14 xl:px-6">
              <Link href="/#how-it-works">How it works</Link>
            </Button>
          </div>
        </div>
        <section
          aria-labelledby="observed-heading"
          className="min-w-0 border-t border-primary/30 pt-7 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0 xl:pl-12"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground xl:text-sm">
            A note on freshness
          </p>
          <h2
            id="observed-heading"
            className="mt-4 text-2xl font-semibold tracking-tight xl:text-3xl"
          >
            Observed, explained.
          </h2>
          <p className="mt-4 max-w-[52ch] text-base leading-relaxed text-muted-foreground xl:text-lg">
            “Observed” means OpenRole saw a listing at its employer ATS source.
            The last-observed timestamp records when that evidence was
            collected.
          </p>
          <p className="mt-5 max-w-[52ch] text-base font-medium leading-relaxed xl:text-lg">
            It is source evidence, not confirmation that an employer is hiring.
          </p>
        </section>
      </section>

      <section
        aria-labelledby="principles-heading"
        className="grid gap-8 border-t border-border py-12 sm:py-16 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.6fr)] lg:gap-[clamp(2rem,4vw,6rem)] xl:py-20"
      >
        <div>
          <h2
            id="principles-heading"
            className="text-[clamp(1.75rem,2.2vw,2.5rem)] font-semibold leading-tight tracking-tight"
          >
            Source evidence.
            <br />
            Useful context.
          </h2>
          <p className="mt-5 max-w-[42ch] text-base leading-relaxed text-muted-foreground xl:text-lg">
            Current coverage is limited to configured Greenhouse sources. Last
            observed shows when a listing was seen in a source check.
          </p>
        </div>
        <dl className="min-w-0 divide-y divide-border">
          <div className="grid gap-3 pb-6 sm:grid-cols-[minmax(10rem,0.35fr)_minmax(0,1fr)] sm:gap-6 xl:gap-8">
            <dt className="text-base font-semibold leading-relaxed xl:text-lg">
              Direct from employers
            </dt>
            <dd className="max-w-[68ch] text-base leading-relaxed text-muted-foreground xl:text-lg">
              Listings come from employer applicant-tracking systems, rather
              than reposted job boards.
            </dd>
          </div>
          <div className="grid gap-3 py-6 sm:grid-cols-[minmax(10rem,0.35fr)_minmax(0,1fr)] sm:gap-6 xl:gap-8">
            <dt className="text-base font-semibold leading-relaxed xl:text-lg">
              Observation timestamps
            </dt>
            <dd className="max-w-[68ch] text-base leading-relaxed text-muted-foreground xl:text-lg">
              Last observed tells you when OpenRole saw a listing. It is
              distinct from an employer’s posting or update date.
            </dd>
          </div>
          <div className="grid gap-3 pt-6 sm:grid-cols-[minmax(10rem,0.35fr)_minmax(0,1fr)] sm:gap-6 xl:gap-8">
            <dt className="text-base font-semibold leading-relaxed xl:text-lg">
              Meaningful changes
            </dt>
            <dd className="max-w-[68ch] text-base leading-relaxed text-muted-foreground xl:text-lg">
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
        className="scroll-mt-8 border-t border-border py-12 sm:py-16 xl:py-20"
      >
        <h2
          id="how-it-works-heading"
          className="text-[clamp(1.75rem,2.2vw,2.5rem)] font-semibold tracking-tight"
        >
          How it works
        </h2>
        <ol className="mt-8 grid gap-8 md:grid-cols-3 md:gap-8 xl:mt-10 xl:gap-12">
          <li>
            <p className="text-sm font-medium tabular-nums text-primary">01</p>
            <h3 className="mt-3 text-lg font-semibold xl:text-xl">
              Check a configured source
            </h3>
            <p className="mt-3 max-w-[52ch] text-base leading-relaxed text-muted-foreground xl:text-lg">
              A source check reads the employer’s ATS listings directly.
            </p>
          </li>
          <li>
            <p className="text-sm font-medium tabular-nums text-primary">02</p>
            <h3 className="mt-3 text-lg font-semibold xl:text-xl">
              Record observations
            </h3>
            <p className="mt-3 max-w-[52ch] text-base leading-relaxed text-muted-foreground xl:text-lg">
              Each observed listing keeps a timestamp of that source evidence.
            </p>
          </li>
          <li>
            <p className="text-sm font-medium tabular-nums text-primary">03</p>
            <h3 className="mt-3 text-lg font-semibold xl:text-xl">
              Preserve material changes
            </h3>
            <p className="mt-3 max-w-[52ch] text-base leading-relaxed text-muted-foreground xl:text-lg">
              Changed listing details are retained alongside earlier versions.
            </p>
          </li>
        </ol>
      </section>

      <section
        aria-labelledby="browse-heading"
        className="mb-12 flex flex-col items-start gap-6 border-t border-border pt-10 sm:mb-16 sm:flex-row sm:items-center sm:justify-between sm:gap-8 sm:pt-12 xl:mb-20 xl:pt-16"
      >
        <div>
          <h2
            id="browse-heading"
            className="text-2xl font-semibold tracking-tight xl:text-3xl"
          >
            Find your next listing.
          </h2>
          <p className="mt-3 text-base leading-relaxed text-muted-foreground xl:text-lg">
            Browse currently observed listings with source freshness in view.
          </p>
        </div>
        <Button asChild variant="outline" className="h-12 shrink-0 px-6 text-base xl:h-14 xl:px-7">
          <Link href="/jobs">Browse jobs</Link>
        </Button>
      </section>
    </>
  );
}
