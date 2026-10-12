export const dashboardSections = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/jobs", label: "Jobs" },
  { href: "/dashboard/sources", label: "Sources" },
  { href: "/dashboard/runs", label: "Pipeline Runs" },
  { href: "/dashboard/quarantine", label: "Quarantine" },
] as const;
export function getDashboardSection(pathname: string) {
  return dashboardSections.find(
    ({ href }) =>
      pathname === href ||
      (href !== "/dashboard" && pathname.startsWith(`${href}/`)),
  );
}
