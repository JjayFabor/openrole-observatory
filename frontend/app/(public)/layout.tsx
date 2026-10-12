import { PublicFooter } from "@/components/public/public-footer";
import { PublicHeader } from "@/components/public/public-header";

export default function PublicLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#public-content"
        className="sr-only fixed left-4 top-4 z-50 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground focus:not-sr-only focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
      >
        Skip to content
      </a>
      <PublicHeader />
      <main
        id="public-content"
        tabIndex={-1}
        className="mx-auto w-full max-w-6xl flex-1 px-5 outline-none sm:px-8 lg:px-10"
      >
        {children}
      </main>
      <PublicFooter />
    </div>
  );
}
