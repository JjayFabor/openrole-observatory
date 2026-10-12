import { sanitizeJobDescription } from "@/lib/jobs/description-html";
import { cn } from "@/lib/utils";

export function JobDescription({
  description,
  emptyText = "—",
  className,
}: {
  description: string | null;
  emptyText?: string;
  className?: string;
}) {
  const html = description ? sanitizeJobDescription(description) : "";
  // This checks presentation only, after the shared sanitizer has removed unsafe content.
  const visibleText = html
    .replace(/<[^>]*>/g, "")
    .replace(/&(?:nbsp|#160|#x0*a0);/gi, " ")
    .trim();
  if (!visibleText) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        {emptyText}
      </p>
    );
  }
  const hasBlockMarkup = /<(?:div|p|ul|ol|li|h3|blockquote)\b/i.test(html);
  return (
    <div
      className={cn(
        "max-w-3xl break-words text-sm leading-7 [overflow-wrap:anywhere] [&_p+p]:mt-3 [&_div+div]:mt-3 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_h3]:mb-2 [&_h3]:mt-5 [&_h3]:text-base [&_h3]:font-semibold [&_h4]:mt-4 [&_h4]:font-semibold [&_h5]:mt-4 [&_h5]:font-semibold [&_h6]:mt-4 [&_h6]:font-semibold [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_a]:focus-visible:rounded [&_a]:focus-visible:outline-2 [&_a]:focus-visible:outline-ring [&_blockquote]:my-4 [&_blockquote]:border-l-2 [&_blockquote]:pl-4",
        !hasBlockMarkup && "whitespace-pre-line",
        className,
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
