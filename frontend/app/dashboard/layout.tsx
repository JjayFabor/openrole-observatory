import type { Metadata } from "next";
import { AppSidebar } from "@/components/dashboard/app-sidebar";
import { DashboardHeader } from "@/components/dashboard/dashboard-header";
import { requireDashboardAccess } from "@/lib/dashboard/access";

export const metadata: Metadata = {
  title: { absolute: "OpenRole Observatory", template: "%s · OpenRole" },
  description: "Internal dashboard for OpenRole Observatory.",
  robots: { index: false, follow: false },
};

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireDashboardAccess();
  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="sr-only fixed left-4 top-4 z-[60] rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground focus:not-sr-only"
      >
        Skip to content
      </a>
      <AppSidebar />
      <div className="md:ml-60">
        <DashboardHeader />
        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto max-w-[1160px] px-5 py-8 outline-none sm:px-8 sm:py-10"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
