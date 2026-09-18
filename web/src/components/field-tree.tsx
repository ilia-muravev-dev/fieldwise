"use client";

import { Check, X } from "lucide-react";
import { ConfidenceChip } from "@/components/confidence-chip";
import { Input } from "@/components/ui/input";
import type { FieldMeta } from "@/lib/api/client";
import { type Leaf, valuesMatch } from "@/lib/fields";
import { displayValue } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  leaves: Leaf[];
  fields: FieldMeta[];
  confidences?: Record<string, number> | null;
  golden?: Record<string, unknown> | null;
  goldenLeaves?: Leaf[];
  showGolden: boolean;
  editing: boolean;
  drafts: Record<string, string>;
  onDraft: (path: string, raw: string) => void;
  hovered: string | null;
  selected: string | null;
  onHover: (path: string | null) => void;
  onSelect: (path: string | null) => void;
}

export function FieldTree({
  leaves,
  fields,
  confidences,
  golden,
  goldenLeaves,
  showGolden,
  editing,
  drafts,
  onDraft,
  hovered,
  selected,
  onHover,
  onSelect,
}: Props) {
  const matcherOf = new Map(fields.map((f) => [f.path, f.matcher]));
  const goldenByPath = new Map((goldenLeaves ?? []).map((l) => [l.path, l.value]));
  const groups: { key: string | undefined; leaves: Leaf[] }[] = [];
  for (const leaf of leaves) {
    const last = groups[groups.length - 1];
    if (last && last.key === leaf.group) last.leaves.push(leaf);
    else groups.push({ key: leaf.group, leaves: [leaf] });
  }

  return (
    <div className="space-y-2">
      {groups.map((group) => (
        <div
          key={group.key ?? `top-${group.leaves[0]?.path}`}
          className={cn(group.key && "rounded-md border bg-muted/20 p-2")}
        >
          {group.key && (
            <p className="mb-1 font-mono text-[11px] text-muted-foreground">{group.key}</p>
          )}
          <ul className="divide-y">
            {group.leaves.map((leaf) => {
              const matcher = matcherOf.get(leaf.schemaPath) ?? "text";
              const isList = Array.isArray(leaf.value);
              const goldenValue = goldenByPath.get(leaf.path);
              const hasGolden = golden !== null && golden !== undefined;
              const match =
                hasGolden && !isList ? valuesMatch(goldenValue, leaf.value, matcher) : null;
              const active = hovered === leaf.path || selected === leaf.path;
              return (
                <li
                  key={leaf.path}
                  className={cn(
                    "grid grid-cols-[1fr_auto] items-center gap-x-3 py-1.5 text-sm transition-colors",
                    active && "bg-amber-400/10",
                  )}
                  onMouseEnter={() => onHover(leaf.path)}
                  onMouseLeave={() => onHover(null)}
                >
                  <button
                    type="button"
                    className="min-w-0 text-left"
                    onClick={() => onSelect(selected === leaf.path ? null : leaf.path)}
                  >
                    <span className="block text-xs text-muted-foreground">{leaf.label}</span>
                    {editing && !isList ? (
                      <Input
                        value={drafts[leaf.path] ?? ""}
                        onChange={(event) => onDraft(leaf.path, event.target.value)}
                        onClick={(event) => event.stopPropagation()}
                        className="mt-0.5 h-7 font-mono text-sm"
                        placeholder="null"
                        inputMode={
                          matcher === "money" || matcher === "integer" ? "decimal" : "text"
                        }
                      />
                    ) : (
                      <span
                        className={cn(
                          "block truncate font-mono",
                          leaf.value == null && "text-muted-foreground",
                        )}
                      >
                        {isList
                          ? `${(leaf.value as unknown[]).length} items`
                          : displayValue(leaf.value)}
                      </span>
                    )}
                    {showGolden && hasGolden && !isList && (
                      <span className="mt-0.5 flex items-center gap-1 text-xs">
                        {match ? (
                          <Check className="size-3 text-emerald-600" aria-label="matches golden" />
                        ) : (
                          <X className="size-3 text-red-600" aria-label="differs from golden" />
                        )}
                        <span className="text-muted-foreground">golden</span>
                        <span className="font-mono">{displayValue(goldenValue)}</span>
                      </span>
                    )}
                  </button>
                  {!isList && <ConfidenceChip confidence={confidences?.[leaf.path]} />}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
