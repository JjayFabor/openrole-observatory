import { Badge } from "@/components/ui/badge";
import type { PipelineStatus } from "@/lib/api/types";
import { getPipelineStatusPresentation } from "@/lib/dashboard/presentation";

export function PipelineStatusBadge({ status }: { status: PipelineStatus }) {
  const presentation = getPipelineStatusPresentation(status);
  return <Badge className={presentation.className}>{presentation.label}</Badge>;
}
