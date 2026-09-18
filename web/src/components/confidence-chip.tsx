import { confidenceTone } from "@/lib/fields";
import { cn } from "@/lib/utils";

const TONES = {
  high: "bg-emerald-500",
  medium: "bg-amber-500",
  low: "bg-red-500",
  none: "bg-muted-foreground/40",
};

export function ConfidenceChip({ confidence }: { confidence: number | undefined }) {
  const tone = confidenceTone(confidence);
  return (
    <span
      className="inline-flex items-center gap-1 font-mono text-[11px] text-muted-foreground"
      title={
        confidence === undefined
          ? "not grounded: no value or no OCR"
          : `grounded in the OCR text at ${(confidence * 100).toFixed(0)}%`
      }
    >
      <span className={cn("inline-block size-2 rounded-full", TONES[tone])} aria-hidden />
      {confidence === undefined ? "—" : `${(confidence * 100).toFixed(0)}%`}
    </span>
  );
}
