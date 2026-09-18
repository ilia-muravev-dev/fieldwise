"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ExtractRequest, unwrap } from "@/lib/api/client";

const ACTIVE = new Set(["queued", "running", "pending"]);

export function useDocuments(params: {
  split?: string;
  q?: string;
  limit: number;
  offset: number;
}) {
  return useQuery({
    queryKey: ["documents", params],
    queryFn: async () => unwrap(await api.GET("/documents", { params: { query: params } })),
    placeholderData: (previous) => previous,
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: ["document", id],
    queryFn: async () =>
      unwrap(await api.GET("/documents/{document_id}", { params: { path: { document_id: id } } })),
    refetchInterval: (query) =>
      query.state.data && ACTIVE.has(query.state.data.ocr_status) ? 2000 : false,
  });
}

export function useOcr(id: string, enabled = true) {
  return useQuery({
    queryKey: ["ocr", id],
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET("/documents/{document_id}/ocr", { params: { path: { document_id: id } } }),
      ),
  });
}

export function useRuns(documentId: string) {
  return useQuery({
    queryKey: ["runs", documentId],
    queryFn: async () =>
      unwrap(
        await api.GET("/documents/{document_id}/runs", {
          params: { path: { document_id: documentId } },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.some((r) => ACTIVE.has(r.status)) ? 2000 : false,
  });
}

export function useRun(id: string | null) {
  return useQuery({
    queryKey: ["run", id],
    enabled: id !== null,
    queryFn: async () =>
      unwrap(await api.GET("/runs/{run_id}", { params: { path: { run_id: id ?? "" } } })),
    refetchInterval: (query) =>
      query.state.data && ACTIVE.has(query.state.data.status) ? 1500 : false,
  });
}

export function useSchema(name: string) {
  return useQuery({
    queryKey: ["schema", name],
    staleTime: 60_000,
    queryFn: async () => unwrap(await api.GET("/schemas/{name}", { params: { path: { name } } })),
  });
}

export function useSchemas() {
  return useQuery({
    queryKey: ["schemas"],
    queryFn: async () => unwrap(await api.GET("/schemas")),
  });
}

export function usePrompts() {
  return useQuery({
    queryKey: ["prompts"],
    staleTime: 60_000,
    queryFn: async () => unwrap(await api.GET("/prompts")),
  });
}

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    staleTime: 60_000,
    queryFn: async () => unwrap(await api.GET("/models")),
  });
}

export function useEvals() {
  return useQuery({
    queryKey: ["evals"],
    queryFn: async () => unwrap(await api.GET("/evals", { params: { query: { limit: 100 } } })),
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "running") ? 5000 : false,
  });
}

export function useEval(id: string) {
  return useQuery({
    queryKey: ["eval", id],
    queryFn: async () =>
      unwrap(await api.GET("/evals/{eval_id}", { params: { path: { eval_id: id } } })),
  });
}

export function useEvalResults(id: string) {
  return useQuery({
    queryKey: ["eval-results", id],
    queryFn: async () =>
      unwrap(await api.GET("/evals/{eval_id}/results", { params: { path: { eval_id: id } } })),
  });
}

export function useEvalComparison(ids: string[]) {
  return useQuery({
    queryKey: ["eval-compare", ids],
    enabled: ids.length > 0,
    queryFn: async () => unwrap(await api.GET("/evals/compare", { params: { query: { ids } } })),
  });
}

export function useUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/documents", { method: "POST", body });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(String(detail.detail ?? response.statusText));
      }
      return (await response.json()) as { id: string; name: string };
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useExtract(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ExtractRequest) =>
      unwrap(
        await api.POST("/documents/{document_id}/extract", {
          params: { path: { document_id: documentId } },
          body,
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs", documentId] });
      queryClient.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
}

export function useSaveGolden(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: Record<string, unknown>) =>
      unwrap(
        await api.PUT("/documents/{document_id}/golden", {
          params: { path: { document_id: documentId } },
          body: { data },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
