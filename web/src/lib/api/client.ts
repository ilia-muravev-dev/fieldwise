import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

/** Typed client for the fieldwise API, reached through the Next.js /api proxy. */
export const api = createClient<paths>({ baseUrl: "/api" });

export type Schemas = components["schemas"];
export type DocumentOut = Schemas["DocumentOut"];
export type DocumentDetail = Schemas["DocumentDetail"];
export type RunOut = Schemas["RunOut"];
export type RunSummary = Schemas["RunSummary"];
export type OcrSpan = Schemas["OcrSpanOut"];
export type EvalOut = Schemas["EvalOut"];
export type EvalResultOut = Schemas["EvalResultOut"];
export type SchemaOut = Schemas["SchemaOut"];
export type FieldMeta = Schemas["FieldMetaOut"];
export type PromptOut = Schemas["PromptOut"];
export type ModelOut = Schemas["ModelOut"];
export type ExtractRequest = Schemas["ExtractRequest"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Throws on error responses so TanStack Query sees them as failures. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    const detail =
      typeof result.error === "object" && result.error && "detail" in result.error
        ? String((result.error as { detail: unknown }).detail)
        : result.response.statusText;
    throw new ApiError(result.response.status, detail || `HTTP ${result.response.status}`);
  }
  return result.data;
}
