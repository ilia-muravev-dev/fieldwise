"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { UploadDropzone } from "@/components/upload-dropzone";
import { useDocuments } from "@/hooks/use-api";
import { usd, when } from "@/lib/format";

const PAGE_SIZE = 25;
const SPLITS = ["all", "test", "validation", "upload"] as const;

function DocumentsTable() {
  const router = useRouter();
  const params = useSearchParams();
  const split = params.get("split") ?? "all";
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? "1"));

  const query = useDocuments({
    split: split === "all" ? undefined : split === "upload" ? undefined : split,
    q: q || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    router.replace(`/documents?${next.toString()}`);
  };

  const items = (query.data?.items ?? []).filter(
    (d) => split !== "upload" || d.source === "upload",
  );
  const total = query.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {SPLITS.map((s) => (
            <Button
              key={s}
              size="sm"
              variant={split === s ? "default" : "ghost"}
              onClick={() => setParam("split", s === "all" ? "" : s)}
            >
              {s}
            </Button>
          ))}
        </div>
        <Input
          placeholder="Search by name…"
          defaultValue={q}
          className="ml-auto w-56"
          onKeyDown={(event) => {
            if (event.key === "Enter") setParam("q", (event.target as HTMLInputElement).value);
          }}
        />
      </div>

      {query.isPending ? (
        <div className="space-y-2">
          {["a", "b", "c", "d", "e", "f"].map((row) => (
            <Skeleton key={row} className="h-9 w-full" />
          ))}
        </div>
      ) : query.isError ? (
        <p className="text-sm text-destructive">Could not load documents: {query.error.message}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Document</TableHead>
              <TableHead>Split</TableHead>
              <TableHead>OCR</TableHead>
              <TableHead>Golden</TableHead>
              <TableHead>Latest run</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead className="text-right">Added</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((doc) => (
              <TableRow
                key={doc.id}
                className="cursor-pointer"
                onClick={() => router.push(`/documents/${doc.id}`)}
              >
                <TableCell className="font-medium">
                  <Link href={`/documents/${doc.id}`} onClick={(e) => e.stopPropagation()}>
                    {doc.name}
                  </Link>
                </TableCell>
                <TableCell>
                  {doc.split ?? <span className="text-muted-foreground">{doc.source}</span>}
                </TableCell>
                <TableCell>
                  <StatusBadge status={doc.ocr_status} />
                </TableCell>
                <TableCell>
                  {doc.has_golden ? (
                    <Badge variant="secondary">labelled</Badge>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell>
                  {doc.latest_run ? (
                    <span className="flex items-center gap-2">
                      <StatusBadge status={doc.latest_run.status} />
                      <span className="text-xs text-muted-foreground">
                        {doc.latest_run.prompt_version} · {doc.latest_run.model}
                      </span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {usd(doc.latest_run?.cost_usd)}
                </TableCell>
                <TableCell className="text-right text-xs text-muted-foreground">
                  {when(doc.created_at)}
                </TableCell>
              </TableRow>
            ))}
            {items.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No documents yet — upload one above or run <code>fieldwise ingest cord</code>.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {total} document{total === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setParam("page", String(page - 1))}
          >
            Previous
          </Button>
          <span>
            {page} / {pages}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= pages}
            onClick={() => setParam("page", String(page + 1))}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="text-sm text-muted-foreground">
            Imported receipts and your uploads, with their latest extraction.
          </p>
        </div>
      </div>
      <UploadDropzone />
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <DocumentsTable />
      </Suspense>
    </div>
  );
}
