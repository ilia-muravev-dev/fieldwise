"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";
import { AccuracyBar } from "@/components/accuracy-bar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEvalComparison } from "@/hooks/use-api";
import type { EvalOut } from "@/lib/api/client";
import { ms, pct, shortId, usd } from "@/lib/format";

function Comparison() {
  const params = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").filter(Boolean);
  const query = useEvalComparison(ids);
  if (ids.length === 0)
    return <p className="text-sm text-muted-foreground">Pick runs on the evals page.</p>;
  if (query.isPending) return <Skeleton className="h-96 w-full" />;
  if (query.isError) return <p className="text-sm text-destructive">{query.error.message}</p>;
  const data = query.data as { runs: EvalOut[]; markdown: string };
  const runs = data.runs;
  const paths: string[] = [];
  for (const run of runs)
    for (const p of run.field_order ?? []) if (!paths.includes(p)) paths.push(p);

  const summary: { label: string; cell: (r: EvalOut) => string }[] = [
    { label: "Field accuracy (strict)", cell: (r) => pct(r.overall_accuracy) },
    { label: "Value accuracy", cell: (r) => pct(r.value_accuracy) },
    { label: "Documents fully correct", cell: (r) => pct(r.doc_exact_rate) },
    { label: "Cost per document", cell: (r) => usd(r.cost_per_doc) },
    { label: "Latency p50", cell: (r) => ms(r.p50_ms) },
    { label: "Not scored (trunc./failed)", cell: (r) => `${r.truncated}/${r.failed}` },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            navigator.clipboard
              .writeText(data.markdown)
              .then(() => toast.success("Markdown table copied"))
          }
        >
          Copy Markdown
        </Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Metric</TableHead>
            {runs.map((r) => (
              <TableHead key={r.id} className="text-right">
                <span className="font-mono text-xs">
                  {r.prompt_version} · {r.model}
                </span>
                <br />
                <span className="font-mono text-[10px] text-muted-foreground">
                  {shortId(r.id)} · k={r.fewshot_k} · OCR {r.use_ocr_text ? "on" : "off"}
                </span>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {summary.map((row) => (
            <TableRow key={row.label}>
              <TableCell className="font-medium">{row.label}</TableCell>
              {runs.map((r) => (
                <TableCell key={r.id} className="text-right font-mono text-xs">
                  {row.cell(r)}
                </TableCell>
              ))}
            </TableRow>
          ))}
          {paths.map((path) => (
            <TableRow key={path}>
              <TableCell className="font-mono text-xs">{path}</TableCell>
              {runs.map((r) => {
                const stats = (r.per_field as Record<string, { accuracy?: number | null }>)[path];
                const list = (r.lists as Record<string, { exact_rate?: number | null }>)[path];
                const value = stats ? stats.accuracy : list ? list.exact_rate : null;
                return (
                  <TableCell key={r.id} className="text-right">
                    <span className="inline-flex items-center gap-2 font-mono text-xs">
                      <AccuracyBar value={value} className="w-16" />
                      {pct(value)}
                    </span>
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default function ComparePage() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Compare runs</h1>
        <p className="text-sm text-muted-foreground">
          Fields as rows, runs as columns — the table the README shows.
        </p>
      </div>
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <Comparison />
      </Suspense>
    </div>
  );
}
