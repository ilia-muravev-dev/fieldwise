"""Renders eval runs as Markdown (committed under docs/evals) and as rich tables (terminal)."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from fieldwise.db.models import EvalRun
from fieldwise.evals.stats import fmt_pct
from fieldwise.schemas.compiler import compile_schema


def ordered_fields(run: EvalRun, table: dict[str, Any]) -> list[str]:
    """JSONB does not keep key order; show fields in schema order instead."""
    try:
        schema_order = [f.path for f in compile_schema(run.schema.json_schema).fields]
    except Exception:  # a run whose schema is gone or invalid still renders
        schema_order = []
    ordered = [path for path in schema_order if path in table]
    return ordered + [path for path in table if path not in ordered]


def _ci(ci: Any) -> str:
    if not ci:
        return "—"
    low, high = ci
    return f"{low * 100:.0f}-{high * 100:.0f}"


def _money(value: float | None) -> str:
    return "—" if value is None else f"${value:.4f}"


def _ms(value: int | None) -> str:
    return "—" if value is None else f"{value} ms"


def config_line(run: EvalRun) -> str:
    return (
        f"prompt **{run.prompt_version}** · model `{run.model}` · effort {run.effort} · "
        f"few-shot k={run.fewshot_k} · OCR text {'on' if run.use_ocr_text else 'off'} · "
        f"provider {run.provider} · split {run.split} · {run.doc_count} docs x {run.reps} rep(s) · "
        f"mode {run.mode}"
    )


def render_markdown(run: EvalRun) -> str:
    lines = [
        f"# Eval {str(run.id)[:8]} — {run.prompt_version} / {run.model}",
        "",
        config_line(run),
        "",
        f"Run at {run.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
        + (f" · {run.notes}" if run.notes else ""),
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Field accuracy (strict, every leaf) | {fmt_pct(run.overall_accuracy)} |",
        f"| Value accuracy (leaves with a golden value) | {fmt_pct(run.value_accuracy)} |",
        f"| Field accuracy (lenient: fuzzy text counts) | {fmt_pct(run.lenient_accuracy)} |",
        f"| Documents fully correct | {fmt_pct(run.doc_exact_rate)} |",
        "| Extractions succeeded / truncated / failed | "
        f"{run.succeeded} / {run.truncated} / {run.failed} |",
        f"| Cost total / per document | {_money(run.cost_usd)} / {_money(run.cost_per_doc)} |",
        f"| Latency p50 / p95 | {_ms(run.p50_ms)} / {_ms(run.p95_ms)} |",
        "",
        "## Per field",
        "",
        "| Field | Matcher | n | Accuracy | 95% CI | Value acc. (n) | wrong | missing | spurious |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for path in ordered_fields(run, run.per_field):
        stats = run.per_field[path]
        counts = stats.get("counts", {})
        lines.append(
            f"| `{path}` | {stats.get('matcher', '')} | {stats.get('n', 0)} | "
            f"{fmt_pct(stats.get('accuracy'))} | {_ci(stats.get('ci'))} | "
            f"{fmt_pct(stats.get('value_accuracy'))} ({stats.get('value_n', 0)}) | "
            f"{counts.get('wrong', 0)} | {counts.get('missing', 0)} | {counts.get('spurious', 0)} |"
        )
    if run.lists:
        lines += [
            "",
            "## Lists",
            "",
            "| List | Docs | Exact match | 95% CI | Item precision | Item recall "
            "| Items (golden / predicted) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for path in ordered_fields(run, run.lists):
            stats = run.lists[path]
            lines.append(
                f"| `{path}` | {stats.get('docs', 0)} | {fmt_pct(stats.get('exact_rate'))} | "
                f"{_ci(stats.get('ci'))} | {fmt_pct(stats.get('item_precision'))} | "
                f"{fmt_pct(stats.get('item_recall'))} | "
                f"{stats.get('golden_items', 0)} / {stats.get('predicted_items', 0)} |"
            )
    if run.errors:
        lines += ["", "## Not scored (infrastructure or output failures)", ""]
        lines += [
            f"- `{e.get('document')}` — {e.get('status')}: {str(e.get('error'))[:200]}"
            for e in run.errors
        ]
    lines.append("")
    return "\n".join(lines)


def render_comparison(runs: list[EvalRun]) -> str:
    """Fields as rows, runs as columns — the table the README shows for v1 → v4."""
    headers = [f"{r.prompt_version} / {r.model}" for r in runs]
    lines = [
        "| Metric | " + " | ".join(headers) + " |",
        "| --- | " + " | ".join("---:" for _ in runs) + " |",
        "| Field accuracy (strict) | "
        + " | ".join(fmt_pct(r.overall_accuracy) for r in runs)
        + " |",
        "| Value accuracy | " + " | ".join(fmt_pct(r.value_accuracy) for r in runs) + " |",
        "| Field accuracy (lenient) | "
        + " | ".join(fmt_pct(r.lenient_accuracy) for r in runs)
        + " |",
        "| Documents fully correct | " + " | ".join(fmt_pct(r.doc_exact_rate) for r in runs) + " |",
        "| Cost per document | " + " | ".join(_money(r.cost_per_doc) for r in runs) + " |",
        "| Latency p50 | " + " | ".join(_ms(r.p50_ms) for r in runs) + " |",
        "| Not scored (trunc./failed) | "
        + " | ".join(f"{r.truncated}/{r.failed}" for r in runs)
        + " |",
    ]
    paths: list[str] = []
    for run in runs:
        for path in ordered_fields(run, run.per_field):
            if path not in paths:
                paths.append(path)
    for path in paths:
        cells = [fmt_pct(r.per_field.get(path, {}).get("accuracy")) for r in runs]
        lines.append(f"| `{path}` | " + " | ".join(cells) + " |")
    list_paths: list[str] = []
    for run in runs:
        for path in run.lists:
            if path not in list_paths:
                list_paths.append(path)
    for path in list_paths:
        cells = [fmt_pct(r.lists.get(path, {}).get("exact_rate")) for r in runs]
        lines.append(f"| `{path}` exact | " + " | ".join(cells) + " |")
    lines += ["", "Runs: " + ", ".join(f"`{str(r.id)[:8]}`" for r in runs), ""]
    return "\n".join(lines)


def print_summary(console: Console, run: EvalRun) -> None:
    table = Table(title=f"eval {str(run.id)[:8]} · {config_line(run).replace('**', '')}")
    for column in (
        "field",
        "matcher",
        "n",
        "accuracy",
        "95% CI",
        "value acc. (n)",
        "wrong/missing/spurious",
    ):
        table.add_column(column, justify="right" if column not in ("field", "matcher") else "left")
    for path in ordered_fields(run, run.per_field):
        stats = run.per_field[path]
        counts = stats.get("counts", {})
        table.add_row(
            path,
            stats.get("matcher", ""),
            str(stats.get("n", 0)),
            fmt_pct(stats.get("accuracy")),
            _ci(stats.get("ci")),
            f"{fmt_pct(stats.get('value_accuracy'))} ({stats.get('value_n', 0)})",
            f"{counts.get('wrong', 0)}/{counts.get('missing', 0)}/{counts.get('spurious', 0)}",
        )
    for path in ordered_fields(run, run.lists):
        stats = run.lists[path]
        table.add_row(
            f"{path} (exact)",
            "list",
            str(stats.get("docs", 0)),
            fmt_pct(stats.get("exact_rate")),
            _ci(stats.get("ci")),
            f"P {fmt_pct(stats.get('item_precision'))} R {fmt_pct(stats.get('item_recall'))}",
            "",
        )
    console.print(table)
    console.print(
        f"overall [bold]{fmt_pct(run.overall_accuracy)}[/bold] strict · "
        f"value accuracy {fmt_pct(run.value_accuracy)} · "
        f"{fmt_pct(run.lenient_accuracy)} lenient · "
        f"docs fully correct {fmt_pct(run.doc_exact_rate)} · "
        f"succeeded/truncated/failed {run.succeeded}/{run.truncated}/{run.failed} · "
        f"cost {_money(run.cost_usd)} ({_money(run.cost_per_doc)}/doc) · "
        f"p50 {_ms(run.p50_ms)} · p95 {_ms(run.p95_ms)}"
    )


def report_path(directory: Path, run: EvalRun) -> Path:
    stamp = run.created_at.astimezone(UTC).strftime("%Y-%m-%d")
    model_slug = run.model.replace("/", "-").replace(":", "-")
    return directory / f"{stamp}-{run.prompt_version}-{model_slug}-{str(run.id)[:8]}.md"


def write_report(directory: Path, run: EvalRun) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = report_path(directory, run)
    path.write_text(render_markdown(run), encoding="utf-8")
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "id": str(run.id),
                "prompt_version": run.prompt_version,
                "model": run.model,
                "effort": run.effort,
                "fewshot_k": run.fewshot_k,
                "use_ocr_text": run.use_ocr_text,
                "provider": run.provider,
                "split": run.split,
                "mode": run.mode,
                "doc_count": run.doc_count,
                "reps": run.reps,
                "succeeded": run.succeeded,
                "truncated": run.truncated,
                "failed": run.failed,
                "overall_accuracy": run.overall_accuracy,
                "lenient_accuracy": run.lenient_accuracy,
                "value_accuracy": run.value_accuracy,
                "doc_exact_rate": run.doc_exact_rate,
                "cost_usd": run.cost_usd,
                "cost_per_doc": run.cost_per_doc,
                "p50_ms": run.p50_ms,
                "p95_ms": run.p95_ms,
                "per_field": run.per_field,
                "lists": run.lists,
                "errors": run.errors,
                "created_at": run.created_at.isoformat(),
                "notes": run.notes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
