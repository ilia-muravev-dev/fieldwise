"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { ExtractRequest, ModelOut, PromptOut } from "@/lib/api/client";

interface Props {
  prompts: PromptOut[];
  models: ModelOut[];
  pending: boolean;
  onSubmit: (body: ExtractRequest) => void;
}

const EFFORTS = ["low", "medium", "high"] as const;

const selectClass =
  "h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm dark:bg-input/30";

export function RunForm({ prompts, models, pending, onSubmit }: Props) {
  const [prompt, setPrompt] = useState(prompts[prompts.length - 1]?.name ?? "v1");
  const [model, setModel] = useState(models[0]?.id ?? "");
  const [effort, setEffort] = useState<(typeof EFFORTS)[number]>("low");
  const [ocrText, setOcrText] = useState<boolean | null>(null);
  const spec = prompts.find((p) => p.name === prompt);

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          schema_name: "receipt",
          prompt,
          model: model || null,
          effort,
          use_ocr_text: ocrText,
        });
      }}
    >
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label htmlFor="prompt">Prompt</Label>
          <select
            id="prompt"
            className={selectClass}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          >
            {prompts.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} · k={p.fewshot_k}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="effort">Effort</Label>
          <select
            id="effort"
            className={selectClass}
            value={effort}
            onChange={(e) => setEffort(e.target.value as (typeof EFFORTS)[number])}
          >
            {EFFORTS.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="model">Model</Label>
        <input
          id="model"
          list="models"
          className={selectClass}
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="model id (server default when empty)"
        />
        <datalist id="models">
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.provider}
            </option>
          ))}
        </datalist>
      </div>
      <div className="flex items-center justify-between">
        <Label htmlFor="ocr-text" className="text-muted-foreground">
          OCR text in the prompt{spec ? ` (default ${spec.use_ocr_text ? "on" : "off"})` : ""}
        </Label>
        <Switch
          id="ocr-text"
          checked={ocrText ?? spec?.use_ocr_text ?? false}
          onCheckedChange={(checked) => setOcrText(checked)}
        />
      </div>
      {spec && <p className="text-xs text-muted-foreground">{spec.notes}</p>}
      <Button type="submit" size="sm" disabled={pending} className="w-full">
        {pending ? "Queuing…" : "Run extraction"}
      </Button>
    </form>
  );
}
