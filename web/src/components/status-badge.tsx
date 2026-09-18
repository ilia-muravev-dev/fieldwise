import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TONES: Record<string, string> = {
  succeeded: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
  done: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
  running: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30",
  queued: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30",
  pending: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
  truncated: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
  failed: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("font-mono text-[11px]", TONES[status] ?? "", className)}
    >
      {status}
    </Badge>
  );
}
