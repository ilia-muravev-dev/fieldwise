"use client";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSchemas } from "@/hooks/use-api";

export default function SchemasPage() {
  const schemas = useSchemas();
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Schemas</h1>
        <p className="text-sm text-muted-foreground">
          What gets extracted, and how each field is graded. Authored as JSON Schema; every leaf is
          nullable for the model.
        </p>
      </div>
      {schemas.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : schemas.isError ? (
        <p className="text-sm text-destructive">{schemas.error.message}</p>
      ) : (
        schemas.data.map((schema) => (
          <section key={schema.id} className="space-y-3">
            <h2 className="font-mono text-lg">
              {schema.name} <span className="text-sm text-muted-foreground">v{schema.version}</span>
            </h2>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Field</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Matcher</TableHead>
                  <TableHead>Description</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {schema.fields.map((field) => (
                  <TableRow key={field.path}>
                    <TableCell className="font-mono text-xs">{field.path}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{field.type}</TableCell>
                    <TableCell className="text-xs">{field.matcher}</TableCell>
                    <TableCell className="text-xs">{field.description}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <details className="rounded-md border p-2 text-xs">
              <summary className="cursor-pointer text-muted-foreground">JSON Schema</summary>
              <pre className="mt-2 overflow-auto font-mono">
                {JSON.stringify(schema.json_schema, null, 2)}
              </pre>
            </details>
          </section>
        ))
      )}
    </div>
  );
}
