import { cn } from "@/lib/utils";

/** A quiet horizontal bar for an accuracy in [0, 1]; null renders as an empty track. */
export function AccuracyBar({
  value,
  className,
}: {
  value: number | null | undefined;
  className?: string;
}) {
  const width = value === null || value === undefined ? 0 : Math.max(0, Math.min(1, value)) * 100;
  const tone =
    value === null || value === undefined
      ? "bg-muted-foreground/30"
      : value >= 0.9
        ? "bg-emerald-500"
        : value >= 0.7
          ? "bg-amber-500"
          : "bg-red-500";
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-24 overflow-hidden rounded-full bg-muted align-middle",
        className,
      )}
      aria-hidden
    >
      <span className={cn("block h-full rounded-full", tone)} style={{ width: `${width}%` }} />
    </span>
  );
}
