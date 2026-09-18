import { StatusBadge } from "@/components/status-badge";
import type { RunOut } from "@/lib/api/client";
import { ms, usd, when } from "@/lib/format";

export function RunStats({ run }: { run: RunOut }) {
  const input = run.input_tokens ?? 0;
  return (
    <div className="space-y-1 text-xs text-muted-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={run.status} />
        <span className="font-mono">
          {run.prompt_version} · {run.model} · {run.effort} · k={run.fewshot_k} · OCR{" "}
          {run.use_ocr_text ? "on" : "off"}
        </span>
      </div>
      {run.status === "succeeded" || run.status === "truncated" ? (
        <p className="font-mono">
          in {input.toLocaleString()} (cache r {run.cache_read_tokens ?? 0} / w{" "}
          {run.cache_write_tokens ?? 0}) · out {(run.output_tokens ?? 0).toLocaleString()} ·{" "}
          {usd(run.cost_usd)} · {ms(run.latency_ms)}
          {run.served_model ? ` · ${run.served_model}` : ""}
        </p>
      ) : null}
      {run.error && <p className="whitespace-pre-wrap break-words text-destructive">{run.error}</p>}
      <p>{when(run.created_at)}</p>
    </div>
  );
}
