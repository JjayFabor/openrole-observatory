import Link from "next/link";
import { BrandLogo } from "@/components/brand-logo";

export function PublicHeader() {
  return (
    <header className="border-b border-border">
      <div className="flex w-full items-center justify-between gap-6 px-5 py-5 sm:px-8 sm:py-6 lg:px-12 xl:px-16 2xl:px-20">
        <Link
          href="/"
          className="shrink-0 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4"
        >
          <BrandLogo variant="accent" className="sm:w-[170px] xl:w-[190px]" />
        </Link>
        <nav aria-label="Public navigation">
          <Link
            href="/jobs"
            className="inline-flex min-h-11 items-center rounded-sm px-2 text-base font-medium text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4 xl:text-lg"
          >
            Jobs
          </Link>
        </nav>
      </div>
    </header>
  );
}
