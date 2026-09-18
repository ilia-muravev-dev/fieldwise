"use client";

import { UploadCloud } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useUpload } from "@/hooks/use-api";
import { cn } from "@/lib/utils";

const ACCEPT = "application/pdf,image/jpeg,image/png,image/webp";

export function UploadDropzone() {
  const router = useRouter();
  const upload = useUpload();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const send = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    upload.mutate(file, {
      onSuccess: (document) => {
        toast.success(`Uploaded ${document.name}`, {
          description: "OCR is running in the background.",
        });
        router.push(`/documents/${document.id}`);
      },
      onError: (error) => toast.error("Upload failed", { description: error.message }),
    });
  };

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: drop target; the button is the keyboard path
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        send(event.dataTransfer.files);
      }}
      className={cn(
        "flex items-center gap-3 rounded-lg border border-dashed px-4 py-3 text-sm transition-colors",
        over ? "border-primary bg-primary/5" : "border-border",
      )}
    >
      <UploadCloud className="size-5 text-muted-foreground" aria-hidden />
      <span className="text-muted-foreground">Drop a PDF or a receipt photo here, or</span>
      <Button
        size="sm"
        variant="outline"
        onClick={() => inputRef.current?.click()}
        disabled={upload.isPending}
      >
        {upload.isPending ? "Uploading…" : "Choose file"}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(event) => {
          send(event.target.files);
          event.target.value = "";
        }}
      />
    </div>
  );
}
