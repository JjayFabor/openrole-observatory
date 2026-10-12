"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BriefcaseBusiness,
  Building2,
  CircleAlert,
  LayoutDashboard,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  dashboardSections,
  getDashboardSection,
} from "@/lib/dashboard/navigation";

const sectionIcons = [
  LayoutDashboard,
  BriefcaseBusiness,
  Building2,
  Workflow,
  CircleAlert,
];
export const navigationItems = dashboardSections.map((section, index) => ({
  ...section,
  icon: sectionIcons[index],
}));

export function DashboardNavigation({
  onNavigate,
}: {
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <nav aria-label="Dashboard" className="space-y-1">
      {navigationItems.map(({ href, label, icon: Icon }) => {
        const active = getDashboardSection(pathname)?.href === href;
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-h-10 items-center gap-3 rounded-md px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "bg-accent font-medium text-accent-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon
              className="size-4 shrink-0"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
