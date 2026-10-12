"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { DashboardBrand } from "./app-sidebar";
import { DashboardNavigation } from "./navigation";
import { getDashboardSection } from "@/lib/dashboard/navigation";

export function DashboardHeader() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const current = getDashboardSection(pathname)?.label ?? "Dashboard";

  return (
    <header className="flex h-[76px] items-center gap-3 border-b border-border bg-card px-5 sm:px-8">
      <div className="md:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open navigation">
              <Menu className="size-5" aria-hidden="true" />
            </Button>
          </SheetTrigger>
          <SheetContent>
            <SheetTitle className="sr-only">Dashboard navigation</SheetTitle>
            <SheetDescription className="sr-only">
              Navigate between OpenRole dashboard sections.
            </SheetDescription>
            <div className="pr-9">
              <DashboardBrand />
            </div>
            <div className="mt-9">
              <DashboardNavigation onNavigate={() => setOpen(false)} />
            </div>
          </SheetContent>
        </Sheet>
      </div>
      <span className="text-sm font-medium">{current}</span>
      <Separator orientation="vertical" className="ml-auto h-4" />
      <div className="flex shrink-0 items-center gap-1.5">
        <Link
          href="/"
          className="rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4 md:hidden"
        >
          <Image
            src="/brand/openrole-mark-v4.svg"
            alt="OpenRole"
            width={96}
            height={96}
            className="size-7"
          />
        </Link>
        <span className="text-xs text-muted-foreground">Observatory</span>
      </div>
    </header>
  );
}
