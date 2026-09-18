"use client";

import Link from "next/link";
import { EvalFieldsTable } from "@/components/eval-fields-table";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEval, useEvalResults } from "@/hooks/use-api";
import { ms, pct, shortId, usd, when } from "@/lib/format";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-xs font-normal text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-mono text-xl">{value}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

export function EvalDetail({ id }: { id: string }) {
  const run = useEval(id);
  const results = useEvalResults(id);
  if (run.isPending) return <Skeleton className="h-96 w-full" />;
  if (run.isError) return <p className="text-sm text-destructive">{run.error.message}</p>;
  const r = run.data;
  const errors = r.errors as { document?: string; status?: string; error?: string }[];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-mono text-xl font-semibold">eval {shortId(r.id)}</h1>
          <StatusBadge status={r.status} />
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          prompt <b>{r.prompt_version}</b> · <span className="font-mono">{r.model}</span> · effort{" "}
          {r.effort} · k={r.fewshot_k} · OCR {r.use_ocr_text ? "on" : "off"} · {r.provider} · split{" "}
          {r.split} · {r.doc_count} docs × {r.reps} rep · {r.mode} · {when(r.created_at)}
          {r.notes ? ` · ${r.notes}` : ""}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat
          label="Field accuracy (strict)"
          value={pct(r.overall_accuracy)}
          hint="every leaf, null agreements count"
        />
        <Stat
          label="Value accuracy"
          value={pct(r.value_accuracy)}
          hint="leaves with a golden value"
        />
        <Stat label="Documents fully correct" value={pct(r.doc_exact_rate)} />
        <Stat
          label="Scored / truncated / failed"
          value={`${r.succeeded} / ${r.truncated} / ${r.failed}`}
        />
        <Stat
          label="Cost per document"
          value={usd(r.cost_per_doc)}
          hint={`total ${usd(r.cost_usd)}`}
        />
        <Stat label="Latency p50 / p95" value={`${ms(r.p50_ms)} / ${ms(r.p95_ms)}`} />
      </div>

      <EvalFieldsTable run={r} />

      {errors.length > 0 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          <p className="mb-1 font-medium">Not scored ({errors.length})</p>
          <ul className="space-y-1 font-mono text-xs">
            {errors.map((e) => (
              <li key={`${e.document}-${e.status}`}>
                {e.document} — {e.status}:{" "}
                <span className="text-muted-foreground">{String(e.error).slice(0, 160)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h2 className="mb-2 text-sm font-medium">Per document</h2>
        {results.data ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead>Rep</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>All fields correct</TableHead>
                <TableHead>Run</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.data.map((row) => (
                <TableRow key={row.extraction_run_id}>
                  <TableCell>
                    <Link
                      href={`/documents/${row.document_id}`}
                      className="underline-offset-2 hover:underline"
                    >
                      {row.document_name}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{row.rep}</TableCell>
                  <TableCell>
                    <StatusBadge status={row.status} />
                  </TableCell>
                  <TableCell className="text-xs">
                    {row.all_correct === null || row.all_correct === undefined
                      ? "—"
                      : row.all_correct
                        ? "yes"
                        : "no"}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {shortId(row.extraction_run_id)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Skeleton className="h-40 w-full" />
        )}
      </div>
    </div>
  );
}
