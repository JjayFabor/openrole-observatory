import { Badge } from "@/components/ui/badge";
import { getSourceActiveLabel } from "@/lib/sources/presentation";

export function SourceStatusBadge({ active }: { active: boolean }) {
  return (
    <Badge
      className={
        active
          ? "border-primary/20 bg-accent text-accent-foreground"
          : "border-border bg-muted text-muted-foreground"
      }
    >
      {getSourceActiveLabel(active)}
    </Badge>
  );
}
