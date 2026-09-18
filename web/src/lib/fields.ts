import type { FieldMeta } from "./api/client";

export type Box = [number, number, number, number];

/** A leaf of an extraction result with its concrete path, e.g. line_items[0].name. */
export interface Leaf {
  path: string; // concrete: line_items[0].name
  schemaPath: string; // as in the schema: line_items[].name
  label: string;
  value: unknown;
  depth: number;
  group?: string; // "line_items[0]" for item fields
}

/** Flattens a result into leaves in schema order, including empty lists and missing keys. */
export function flattenResult(
  result: Record<string, unknown> | null | undefined,
  fields: FieldMeta[],
): Leaf[] {
  const byPath = new Map(fields.map((f) => [f.path, f]));
  const leaves: Leaf[] = [];
  const roots = fields.filter((f) => !f.path.includes(".") && !f.path.includes("[]"));

  const walk = (
    meta: FieldMeta,
    value: unknown,
    concrete: string,
    depth: number,
    group?: string,
  ) => {
    if (meta.matcher === "list") {
      const items = Array.isArray(value) ? value : [];
      if (items.length === 0) {
        leaves.push({
          path: concrete,
          schemaPath: meta.path,
          label: labelOf(meta.path),
          value: [],
          depth,
          group,
        });
        return;
      }
      items.forEach((item, index) => {
        const itemPath = `${concrete}[${index}]`;
        for (const childPath of meta.children ?? []) {
          const child = byPath.get(childPath);
          if (!child) continue;
          const key = childPath.slice(childPath.lastIndexOf(".") + 1);
          const childValue =
            item && typeof item === "object" ? (item as Record<string, unknown>)[key] : undefined;
          walk(child, childValue, `${itemPath}.${key}`, depth + 1, itemPath);
        }
      });
      return;
    }
    if (meta.matcher === "object") {
      for (const childPath of meta.children ?? []) {
        const child = byPath.get(childPath);
        if (!child) continue;
        const key = childPath.slice(childPath.lastIndexOf(".") + 1);
        const childValue =
          value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined;
        walk(child, childValue, `${concrete}.${key}`, depth + 1, group);
      }
      return;
    }
    leaves.push({
      path: concrete,
      schemaPath: meta.path,
      label: labelOf(meta.path),
      value,
      depth,
      group,
    });
  };

  for (const root of roots) {
    walk(root, result?.[root.path], root.path, 0);
  }
  return leaves;
}

export function labelOf(path: string): string {
  const last = path.slice(path.lastIndexOf(".") + 1).replace("[]", "");
  return last.replace(/_/g, " ");
}

/** Scales a box in stored-page pixels to the rendered image size. */
export function scaleBox(
  box: Box,
  natural: { width: number; height: number },
  rendered: { width: number; height: number },
): Box {
  const sx = rendered.width / natural.width;
  const sy = rendered.height / natural.height;
  return [box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy];
}

/** Sets a value at a concrete path ("line_items[1].name") in a deep copy of the object. */
export function setAtPath(
  target: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  const copy = structuredClone(target);
  const tokens = path.match(/[^.[\]]+|\[\d+\]/g) ?? [];
  let cursor: unknown = copy;
  tokens.forEach((token, index) => {
    const key: string | number = token.startsWith("[") ? Number(token.slice(1, -1)) : token;
    const last = index === tokens.length - 1;
    const container = cursor as Record<string | number, unknown>;
    if (last) {
      container[key] = value;
      return;
    }
    if (container[key] === undefined || container[key] === null) {
      const next = tokens[index + 1];
      container[key] = next?.startsWith("[") ? [] : {};
    }
    cursor = container[key];
  });
  return copy;
}

export function confidenceTone(confidence: number | undefined): "high" | "medium" | "low" | "none" {
  if (confidence === undefined) return "none";
  if (confidence >= 0.9) return "high";
  if (confidence >= 0.7) return "medium";
  return "low";
}

/** Golden vs. predicted, the way the eval's matchers see it (numbers within 0.005, text normalised). */
export function valuesMatch(golden: unknown, predicted: unknown, matcher: string): boolean {
  const empty = (v: unknown) => v === null || v === undefined || v === "";
  if (empty(golden) && empty(predicted)) return true;
  if (empty(golden) || empty(predicted)) return false;
  if (matcher === "money" || matcher === "number" || matcher === "integer") {
    const g = Number(golden);
    const p = Number(predicted);
    return Number.isFinite(g) && Number.isFinite(p) && Math.abs(g - p) <= 0.005;
  }
  if (matcher === "boolean") return Boolean(golden) === Boolean(predicted);
  return normaliseText(golden) === normaliseText(predicted);
}

export function normaliseText(value: unknown): string {
  return String(value)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s%&+/@-]/gu, " ")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
}

/** Turns what a reviewer typed into the value the schema expects; empty means null. */
export function parseDraft(raw: string, matcher: string): unknown {
  const text = raw.trim();
  if (text === "" || text.toLowerCase() === "null") return null;
  if (matcher === "money" || matcher === "number") {
    const number = Number(text.replace(/[^\d.-]/g, ""));
    return Number.isFinite(number) ? number : null;
  }
  if (matcher === "integer") {
    const number = Number.parseInt(text.replace(/[^\d-]/g, ""), 10);
    return Number.isFinite(number) ? number : null;
  }
  if (matcher === "boolean") return ["true", "yes", "1"].includes(text.toLowerCase());
  return text;
}
