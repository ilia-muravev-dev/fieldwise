"""Prompt versions are files in this package plus a spec of what each one switches on.
Adding a version = adding a file and a row here, then measuring it (docs/evals)."""

import json
from dataclasses import dataclass
from importlib import resources
from string import Template
from typing import Any


@dataclass(frozen=True)
class PromptSpec:
    name: str
    notes: str
    use_ocr_text: bool = False
    fewshot_k: int = 0
    use_evidence: bool = False
    consistency_check: bool = False

    def template(self) -> str:
        return resources.files(__package__).joinpath(f"{self.name}.md").read_text(encoding="utf-8")

    def render_system(self, authored_schema: dict[str, Any]) -> str:
        schema_json = json.dumps(authored_schema, indent=2, ensure_ascii=False)
        return Template(self.template()).safe_substitute(schema_json=schema_json).strip()


PROMPTS: dict[str, PromptSpec] = {
    "v1": PromptSpec(name="v1", notes="Baseline: instructions and the schema; the image only."),
}


def get_prompt(name: str) -> PromptSpec:
    try:
        return PROMPTS[name]
    except KeyError as error:
        raise KeyError(f"unknown prompt version {name!r}; known: {sorted(PROMPTS)}") from error
