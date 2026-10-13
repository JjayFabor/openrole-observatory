import Link from "next/link";
import { BrandLogo } from "@/components/brand-logo";

export function PublicFooter() {
  return (
    <footer className="border-t border-foreground bg-foreground text-primary-foreground">
      <div className="flex w-full flex-col gap-5 px-5 py-8 text-base sm:flex-row sm:items-center sm:justify-between sm:px-8 sm:py-10 lg:px-12 xl:px-16 2xl:px-20">
        <Link
          href="/"
          className="self-start rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-primary-foreground focus-visible:ring-offset-4 focus-visible:ring-offset-foreground"
        >
          <BrandLogo variant="inverse" />
        </Link>
        <p className="text-primary-foreground/80">Direct-source job intelligence.</p>
      </div>
    </footer>
  );
}
