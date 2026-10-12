import { BrandLogo } from "@/components/brand-logo";
import { DashboardNavigation } from "./navigation";

export function DashboardBrand() {
  return (
    <div>
      <BrandLogo />
      <p className="mt-1 text-xs text-muted-foreground">Observatory</p>
    </div>
  );
}

export function AppSidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-border bg-sidebar md:flex">
      <div className="flex h-[76px] items-center px-5">
        <DashboardBrand />
      </div>
      <div className="px-3 pt-4">
        <p className="mb-3 px-3 text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground">
          Workspace
        </p>
        <DashboardNavigation />
      </div>
      <div className="mt-auto border-t border-border px-6 py-5">
        <p className="text-xs font-medium">Internal dashboard</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Observe the system.
          <br />
          Follow the data.
        </p>
      </div>
    </aside>
  );
}
