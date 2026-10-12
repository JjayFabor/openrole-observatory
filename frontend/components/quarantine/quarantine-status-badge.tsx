import { Badge } from "@/components/ui/badge";
import type { QuarantineStatus } from "@/lib/api/types";
import { getQuarantineStatusLabel } from "@/lib/quarantine/presentation";

export function QuarantineStatusBadge({
  status,
}: {
  status: QuarantineStatus;
}) {
  return (
    <Badge
      className={
        status === "resolved"
          ? "border-primary/20 bg-accent text-accent-foreground"
          : "border-border bg-muted text-muted-foreground"
      }
    >
      {getQuarantineStatusLabel(status)}
    </Badge>
  );
}
