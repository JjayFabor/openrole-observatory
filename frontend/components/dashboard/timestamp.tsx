import {
  formatAbsoluteTimestamp,
  formatRelativeTimestamp,
} from "@/lib/dashboard/presentation";

export function Timestamp({
  value,
  now,
}: {
  value: string | null;
  now: number;
}) {
  if (value === null)
    return <span className="text-sm text-muted-foreground">Never</span>;
  return (
    <div>
      <time dateTime={value} className="block text-sm">
        {formatRelativeTimestamp(value, now)}
      </time>
      <span className="mt-1 block text-xs leading-5 text-muted-foreground">
        {formatAbsoluteTimestamp(value)}
      </span>
    </div>
  );
}
