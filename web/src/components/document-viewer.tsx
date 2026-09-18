"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { DocumentDetail, OcrSpan } from "@/lib/api/client";
import type { Box } from "@/lib/fields";
import { cn } from "@/lib/utils";

interface Props {
  document: DocumentDetail;
  spans: OcrSpan[];
  showSpans: boolean;
  /** Boxes to emphasise (the hovered or selected field). */
  highlight: Box[];
  onSpanClick?: (span: OcrSpan) => void;
}

function pctStyle(box: Box, width: number, height: number) {
  return {
    left: `${(box[0] / width) * 100}%`,
    top: `${(box[1] / height) * 100}%`,
    width: `${((box[2] - box[0]) / width) * 100}%`,
    height: `${((box[3] - box[1]) / height) * 100}%`,
  };
}

/** The page image with OCR spans and field boxes drawn over it, scaled by percentages so it
 * stays aligned at any width. */
export function DocumentViewer({ document, spans, showSpans, highlight, onSpanClick }: Props) {
  const [pageIndex, setPageIndex] = useState(0);
  const page = document.pages[pageIndex];
  if (!page) return <p className="text-sm text-muted-foreground">No rendered pages.</p>;
  const pageSpans = spans.filter((s) => s.page === page.page);

  return (
    <div className="space-y-2">
      {document.pages.length > 1 && (
        <div className="flex items-center gap-2 text-sm">
          <Button
            size="sm"
            variant="outline"
            disabled={pageIndex === 0}
            onClick={() => setPageIndex(pageIndex - 1)}
          >
            ‹
          </Button>
          <span>
            page {page.page} / {document.pages.length}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={pageIndex >= document.pages.length - 1}
            onClick={() => setPageIndex(pageIndex + 1)}
          >
            ›
          </Button>
        </div>
      )}
      <div className="relative w-full overflow-hidden rounded-lg border bg-muted/30">
        {/* biome-ignore lint/performance/noImgElement: dynamic API-served page image, no optimisation wanted */}
        <img
          src={`/api${page.url}`}
          alt={`${document.name}, page ${page.page}`}
          width={page.width}
          height={page.height}
          className="block h-auto w-full select-none"
          draggable={false}
        />
        {showSpans &&
          pageSpans.map((span) => (
            <button
              key={`${span.box.join(",")}:${span.text}`}
              type="button"
              title={span.text}
              onClick={() => onSpanClick?.(span)}
              className="absolute rounded-[2px] border border-sky-500/50 bg-sky-400/10 transition-colors hover:bg-sky-400/30"
              style={pctStyle(span.box as Box, page.width, page.height)}
            />
          ))}
        {highlight.map((box) => (
          <div
            key={box.join(",")}
            className={cn(
              "pointer-events-none absolute rounded-[3px] border-2 border-amber-500 bg-amber-400/25",
              "shadow-[0_0_0_9999px_rgba(0,0,0,0.12)]",
            )}
            style={pctStyle(box, page.width, page.height)}
          />
        ))}
      </div>
    </div>
  );
}
