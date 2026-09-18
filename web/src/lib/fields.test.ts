import { describe, expect, it } from "vitest";
import type { FieldMeta } from "./api/client";
import { confidenceTone, flattenResult, scaleBox, setAtPath } from "./fields";

const fields: FieldMeta[] = [
  {
    path: "line_items",
    type: "array",
    matcher: "list",
    description: "",
    children: ["line_items[].name", "line_items[].line_total"],
  },
  { path: "line_items[].name", type: "string", matcher: "text", description: "", children: [] },
  {
    path: "line_items[].line_total",
    type: "number",
    matcher: "money",
    description: "",
    children: [],
  },
  { path: "total", type: "number", matcher: "money", description: "", children: [] },
];

describe("flattenResult", () => {
  it("walks lists into concrete paths in schema order", () => {
    const leaves = flattenResult(
      { total: 45500, line_items: [{ name: "EGG TART", line_total: 13000 }, { name: "X" }] },
      fields,
    );
    expect(leaves.map((l) => l.path)).toEqual([
      "line_items[0].name",
      "line_items[0].line_total",
      "line_items[1].name",
      "line_items[1].line_total",
      "total",
    ]);
    expect(leaves[1]).toMatchObject({
      schemaPath: "line_items[].line_total",
      value: 13000,
      group: "line_items[0]",
      depth: 1,
    });
    expect(leaves[3].value).toBeUndefined();
    expect(leaves[4]).toMatchObject({ label: "total", value: 45500, depth: 0 });
  });

  it("keeps empty lists visible and tolerates a missing result", () => {
    expect(flattenResult({ total: null }, fields).map((l) => [l.path, l.value])).toEqual([
      ["line_items", []],
      ["total", null],
    ]);
    expect(flattenResult(undefined, fields)).toHaveLength(2);
  });
});

describe("helpers", () => {
  it("scales boxes to the rendered image", () => {
    expect(
      scaleBox([100, 200, 300, 400], { width: 1000, height: 2000 }, { width: 500, height: 1000 }),
    ).toEqual([50, 100, 150, 200]);
  });

  it("sets values at concrete paths without mutating the source", () => {
    const source = { total: 1, line_items: [{ name: "A" }] };
    const updated = setAtPath(source, "line_items[1].name", "B");
    expect(updated).toEqual({ total: 1, line_items: [{ name: "A" }, { name: "B" }] });
    expect(source.line_items).toHaveLength(1);
    expect(setAtPath({}, "total", 5)).toEqual({ total: 5 });
  });

  it("maps confidence to a tone", () => {
    expect(confidenceTone(0.95)).toBe("high");
    expect(confidenceTone(0.8)).toBe("medium");
    expect(confidenceTone(0.2)).toBe("low");
    expect(confidenceTone(undefined)).toBe("none");
  });
});

describe("review helpers", () => {
  it("compares values like the eval matchers", async () => {
    const { valuesMatch, parseDraft } = await import("./fields");
    expect(valuesMatch(45500, 45500.004, "money")).toBe(true);
    expect(valuesMatch(45500, 45000, "money")).toBe(false);
    expect(valuesMatch("NASI GORENG", "nasi  goreng!", "text")).toBe(true);
    expect(valuesMatch(null, undefined, "money")).toBe(true);
    expect(valuesMatch(null, 1, "money")).toBe(false);
    expect(parseDraft(" 45,500 ", "money")).toBe(45500);
    expect(parseDraft("2 x", "integer")).toBe(2);
    expect(parseDraft("", "text")).toBeNull();
    expect(parseDraft("EGG TART", "text")).toBe("EGG TART");
  });
});
