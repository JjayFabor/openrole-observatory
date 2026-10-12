import Link from "next/link";
import { BrandLogo } from "@/components/brand-logo";

export function PublicHeader() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-5 py-5 sm:px-8 lg:px-10">
        <Link
          href="/"
          className="shrink-0 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4"
        >
          <BrandLogo variant="accent" className="sm:w-[170px]" />
        </Link>
        <nav aria-label="Public navigation">
          <Link
            href="/jobs"
            className="rounded-sm text-sm font-medium text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4"
          >
            Jobs
          </Link>
        </nav>
      </div>
    </header>
  );
}
