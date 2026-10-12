import { Badge } from "@/components/ui/badge";
import type { JobLifecycleStatus } from "@/lib/api/types";
import { getLifecycleLabel } from "@/lib/jobs/presentation";

export function LifecycleBadge({ status }: { status: JobLifecycleStatus }) {
  return (
    <Badge
      className={
        status === "observed"
          ? "border-primary/20 bg-accent text-accent-foreground"
          : "border-border bg-muted text-muted-foreground"
      }
    >
      {getLifecycleLabel(status)}
    </Badge>
  );
}
