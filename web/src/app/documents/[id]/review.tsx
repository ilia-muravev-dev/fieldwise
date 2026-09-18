"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { DocumentViewer } from "@/components/document-viewer";
import { FieldTree } from "@/components/field-tree";
import { RunForm } from "@/components/run-form";
import { RunStats } from "@/components/run-stats";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  useDocument,
  useExtract,
  useModels,
  useOcr,
  usePrompts,
  useRun,
  useRuns,
  useSaveGolden,
  useSchema,
} from "@/hooks/use-api";
import type { OcrSpan } from "@/lib/api/client";
import { type Box, flattenResult, parseDraft, setAtPath } from "@/lib/fields";
import { displayValue, shortId, when } from "@/lib/format";

export function Review({ documentId }: { documentId: string }) {
  const document = useDocument(documentId);
  const runs = useRuns(documentId);
  const schema = useSchema("receipt");
  const prompts = usePrompts();
  const models = useModels();
  const ocr = useOcr(documentId, document.data?.ocr_status === "done");
  const extract = useExtract(documentId);
  const saveGolden = useSaveGolden(documentId);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [showGolden, setShowGolden] = useState(true);
  const [showSpans, setShowSpans] = useState(false);
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  // Default to the newest run once; a run queued from this page selects itself.
  useEffect(() => {
    const newest = runs.data?.[0];
    if (newest && selectedRunId === null) setSelectedRunId(newest.id);
  }, [runs.data, selectedRunId]);

  const run = useRun(selectedRunId);
  const fields = schema.data?.fields ?? [];
  const golden = document.data?.golden?.data ?? null;
  const leaves = useMemo(
    () => flattenResult(run.data?.result ?? null, fields),
    [run.data?.result, fields],
  );
  const goldenLeaves = useMemo(() => flattenResult(golden, fields), [golden, fields]);

  const highlight: Box[] = useMemo(() => {
    const path = hovered ?? selected;
    if (!path || !run.data?.boxes) return [];
    return (run.data.boxes[path] ?? []) as Box[];
  }, [hovered, selected, run.data?.boxes]);

  const startEditing = () => {
    const base = run.data?.result ?? golden ?? {};
    const initial: Record<string, string> = {};
    for (const leaf of flattenResult(base, fields)) {
      if (!Array.isArray(leaf.value))
        initial[leaf.path] = leaf.value == null ? "" : String(leaf.value);
    }
    setDrafts(initial);
    setEditing(true);
  };

  const saveCorrection = () => {
    const matcherOf = new Map(fields.map((f) => [f.path, f.matcher]));
    let data: Record<string, unknown> = structuredClone(run.data?.result ?? golden ?? {});
    for (const leaf of flattenResult(data, fields)) {
      if (Array.isArray(leaf.value)) continue;
      const raw = drafts[leaf.path];
      if (raw === undefined) continue;
      data = setAtPath(data, leaf.path, parseDraft(raw, matcherOf.get(leaf.schemaPath) ?? "text"));
    }
    saveGolden.mutate(data, {
      onSuccess: () => {
        setEditing(false);
        toast.success("Correction saved", {
          description: "It is now this document's golden label and a few-shot example.",
        });
      },
      onError: (error) => toast.error("Could not save", { description: error.message }),
    });
  };

  const onSpanClick = (span: OcrSpan) => {
    if (!run.data?.boxes) return;
    const [x0, y0, x1, y1] = span.box;
    const hit = Object.entries(run.data.boxes).find(([, boxes]) =>
      boxes.some((b) => b[0] < x1 && b[2] > x0 && b[1] < y1 && b[3] > y0),
    );
    setSelected(hit ? hit[0] : null);
  };

  if (document.isPending) return <Skeleton className="h-[70vh] w-full" />;
  if (document.isError) return <p className="text-sm text-destructive">{document.error.message}</p>;
  const doc = document.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{doc.name}</h1>
        <StatusBadge status={doc.ocr_status} />
        {doc.split && <Badge variant="secondary">{doc.split}</Badge>}
        {doc.golden && (
          <Badge variant="outline" className="font-mono text-[11px]">
            golden: {doc.golden.source}
          </Badge>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          {doc.page_count} page{doc.page_count === 1 ? "" : "s"} · added {when(doc.created_at)}
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_440px]">
        <section className="space-y-2">
          <div className="flex items-center gap-4 text-sm">
            <span className="flex items-center gap-2">
              <Switch id="spans" checked={showSpans} onCheckedChange={setShowSpans} />
              <Label htmlFor="spans">OCR boxes</Label>
            </span>
            <span className="text-xs text-muted-foreground">
              {(hovered ?? selected)
                ? `highlighting ${hovered ?? selected}`
                : "hover a field to see where it was read"}
            </span>
          </div>
          <DocumentViewer
            document={doc}
            spans={ocr.data ?? []}
            showSpans={showSpans}
            highlight={highlight}
            onSpanClick={onSpanClick}
          />
          {doc.ocr_text && (
            <details className="rounded-md border p-2 text-xs">
              <summary className="cursor-pointer text-muted-foreground">OCR text</summary>
              <pre className="mt-2 whitespace-pre-wrap font-mono">{doc.ocr_text}</pre>
            </details>
          )}
        </section>

        <aside className="space-y-4">
          <div className="rounded-lg border p-3">
            <h2 className="mb-2 text-sm font-medium">Run extraction</h2>
            {prompts.data && models.data ? (
              <RunForm
                prompts={prompts.data}
                models={models.data}
                pending={extract.isPending}
                onSubmit={(body) =>
                  extract.mutate(body, {
                    onSuccess: (queued) => {
                      setSelectedRunId(queued.id);
                      toast.message("Extraction queued", {
                        description: `run ${shortId(queued.id)}`,
                      });
                    },
                    onError: (error) =>
                      toast.error("Could not queue", { description: error.message }),
                  })
                }
              />
            ) : (
              <Skeleton className="h-32 w-full" />
            )}
          </div>

          <div className="rounded-lg border p-3">
            <div className="mb-2 flex items-center gap-2">
              <h2 className="text-sm font-medium">Runs</h2>
              {runs.data && runs.data.length > 0 && (
                <select
                  className="ml-auto h-7 max-w-[240px] rounded-md border border-input bg-transparent px-2 text-xs dark:bg-input/30"
                  value={selectedRunId ?? ""}
                  onChange={(event) => setSelectedRunId(event.target.value)}
                >
                  {runs.data.map((r) => (
                    <option key={r.id} value={r.id}>
                      {shortId(r.id)} · {r.status} · {r.prompt_version} · {r.model}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {run.data ? (
              <RunStats run={run.data} />
            ) : (
              <p className="text-xs text-muted-foreground">No extraction yet.</p>
            )}
          </div>

          <div className="rounded-lg border p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-medium">Fields</h2>
              <span className="ml-auto flex items-center gap-2 text-xs">
                <Switch
                  id="golden"
                  checked={showGolden}
                  onCheckedChange={setShowGolden}
                  disabled={!golden}
                />
                <Label htmlFor="golden" className="text-muted-foreground">
                  golden
                </Label>
              </span>
              {editing ? (
                <>
                  <Button size="sm" onClick={saveCorrection} disabled={saveGolden.isPending}>
                    {saveGolden.isPending ? "Saving…" : "Save correction"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={startEditing}
                  disabled={!run.data?.result && !golden}
                >
                  Edit values
                </Button>
              )}
            </div>
            {run.data?.result || golden ? (
              <FieldTree
                leaves={run.data?.result ? leaves : goldenLeaves}
                fields={fields}
                confidences={run.data?.confidences}
                golden={golden}
                goldenLeaves={goldenLeaves}
                showGolden={showGolden}
                editing={editing}
                drafts={drafts}
                onDraft={(path, raw) => setDrafts((d) => ({ ...d, [path]: raw }))}
                hovered={hovered}
                selected={selected}
                onHover={setHovered}
                onSelect={setSelected}
              />
            ) : (
              <p className="text-xs text-muted-foreground">Run an extraction to see fields here.</p>
            )}
            {selected && run.data?.evidence?.[selected] !== undefined && (
              <p className="mt-2 text-xs text-muted-foreground">
                evidence:{" "}
                <span className="font-mono">{displayValue(run.data.evidence[selected])}</span>
              </p>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
