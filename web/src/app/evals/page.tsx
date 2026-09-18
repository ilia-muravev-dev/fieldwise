"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEvals } from "@/hooks/use-api";
import { ms, pct, shortId, usd, when } from "@/lib/format";

export default function EvalsPage() {
  const evals = useEvals();
  const router = useRouter();
  const [picked, setPicked] = useState<string[]>([]);
  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Evals</h1>
          <p className="text-sm text-muted-foreground">
            Every measurement of a prompt × model configuration on a labelled split. Pick runs to
            compare them field by field.
          </p>
        </div>
        <Button
          className="ml-auto"
          size="sm"
          disabled={picked.length < 2}
          onClick={() => router.push(`/evals/compare?ids=${picked.join(",")}`)}
        >
          Compare {picked.length > 0 ? `(${picked.length})` : ""}
        </Button>
      </div>
      {evals.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : evals.isError ? (
        <p className="text-sm text-destructive">{evals.error.message}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Run</TableHead>
              <TableHead>Prompt</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>k / OCR</TableHead>
              <TableHead>Split</TableHead>
              <TableHead className="text-right">Scored</TableHead>
              <TableHead className="text-right">Strict</TableHead>
              <TableHead className="text-right">Value</TableHead>
              <TableHead className="text-right">Docs ok</TableHead>
              <TableHead className="text-right">$/doc</TableHead>
              <TableHead className="text-right">p50</TableHead>
              <TableHead className="text-right">When</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {evals.data.map((run) => (
              <TableRow key={run.id}>
                <TableCell>
                  <Checkbox
                    checked={picked.includes(run.id)}
                    onCheckedChange={() => toggle(run.id)}
                    aria-label={`select ${shortId(run.id)}`}
                  />
                </TableCell>
                <TableCell>
                  <Link
                    href={`/evals/${run.id}`}
                    className="font-mono text-xs underline-offset-2 hover:underline"
                  >
                    {shortId(run.id)}
                  </Link>{" "}
                  <StatusBadge status={run.status} />
                </TableCell>
                <TableCell className="font-mono text-xs">{run.prompt_version}</TableCell>
                <TableCell className="max-w-[220px] truncate font-mono text-xs" title={run.model}>
                  {run.model}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {run.fewshot_k} / {run.use_ocr_text ? "on" : "off"}
                </TableCell>
                <TableCell className="text-xs">{run.split}</TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {run.succeeded}/{run.doc_count * run.reps}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {pct(run.overall_accuracy)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {pct(run.value_accuracy)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {pct(run.doc_exact_rate)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {usd(run.cost_per_doc)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">{ms(run.p50_ms)}</TableCell>
                <TableCell className="text-right text-xs text-muted-foreground">
                  {when(run.created_at)}
                </TableCell>
              </TableRow>
            ))}
            {evals.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={13} className="py-10 text-center text-muted-foreground">
                  No eval runs yet — run <code>fieldwise eval run --prompt v1 --limit 20</code>.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
