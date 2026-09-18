import { AccuracyBar } from "@/components/accuracy-bar";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { EvalOut } from "@/lib/api/client";
import { pct } from "@/lib/format";

type FieldStats = {
  matcher?: string;
  n?: number;
  accuracy?: number | null;
  ci?: [number, number] | null;
  value_accuracy?: number | null;
  value_n?: number;
  counts?: Record<string, number>;
};

type ListStats = {
  docs?: number;
  exact_rate?: number | null;
  ci?: [number, number] | null;
  item_precision?: number | null;
  item_recall?: number | null;
};

function ci(value: [number, number] | null | undefined): string {
  return value ? `${(value[0] * 100).toFixed(0)}–${(value[1] * 100).toFixed(0)}` : "—";
}

export function EvalFieldsTable({ run }: { run: EvalOut }) {
  const perField = run.per_field as Record<string, FieldStats>;
  const lists = run.lists as Record<string, ListStats>;
  const order = run.field_order ?? Object.keys(perField);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Field</TableHead>
          <TableHead>Matcher</TableHead>
          <TableHead className="text-right">n</TableHead>
          <TableHead>Accuracy</TableHead>
          <TableHead className="text-right">95% CI</TableHead>
          <TableHead className="text-right">Value acc. (n)</TableHead>
          <TableHead className="text-right">wrong / missing / spurious</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {order
          .filter((path) => path in perField)
          .map((path) => {
            const stats = perField[path];
            const counts = stats.counts ?? {};
            return (
              <TableRow key={path}>
                <TableCell className="font-mono text-xs">{path}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{stats.matcher}</TableCell>
                <TableCell className="text-right font-mono text-xs">{stats.n}</TableCell>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <AccuracyBar value={stats.accuracy} />
                    <span className="font-mono text-xs">{pct(stats.accuracy)}</span>
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono text-xs text-muted-foreground">
                  {ci(stats.ci)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {pct(stats.value_accuracy)}{" "}
                  <span className="text-muted-foreground">({stats.value_n ?? 0})</span>
                </TableCell>
                <TableCell className="text-right font-mono text-xs text-muted-foreground">
                  {counts.wrong ?? 0} / {counts.missing ?? 0} / {counts.spurious ?? 0}
                </TableCell>
              </TableRow>
            );
          })}
        {order
          .filter((path) => path in lists)
          .map((path) => {
            const stats = lists[path];
            return (
              <TableRow key={`${path}-list`}>
                <TableCell className="font-mono text-xs">{path} (exact)</TableCell>
                <TableCell className="text-xs text-muted-foreground">list</TableCell>
                <TableCell className="text-right font-mono text-xs">{stats.docs}</TableCell>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <AccuracyBar value={stats.exact_rate} />
                    <span className="font-mono text-xs">{pct(stats.exact_rate)}</span>
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono text-xs text-muted-foreground">
                  {ci(stats.ci)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs" colSpan={2}>
                  items P {pct(stats.item_precision)} · R {pct(stats.item_recall)}
                </TableCell>
              </TableRow>
            );
          })}
      </TableBody>
    </Table>
  );
}
