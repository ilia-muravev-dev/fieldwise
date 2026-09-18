from fastapi import APIRouter

from fieldwise import __version__
from fieldwise.api.models import ModelOut, PromptOut
from fieldwise.config import get_settings
from fieldwise.extraction.pricing import PRICES
from fieldwise.extraction.prompts.registry import PROMPTS

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/prompts", response_model=list[PromptOut])
def prompts() -> list[PromptOut]:
    return [
        PromptOut(
            name=spec.name,
            notes=spec.notes,
            use_ocr_text=spec.use_ocr_text,
            fewshot_k=spec.fewshot_k,
            use_evidence=spec.use_evidence,
            consistency_check=spec.consistency_check,
        )
        for spec in PROMPTS.values()
    ]


@router.get("/models", response_model=list[ModelOut])
def models() -> list[ModelOut]:
    settings = get_settings()
    known = [
        ModelOut(id=model, provider="anthropic", input_per_mtok=p.input, output_per_mtok=p.output)
        for model, p in PRICES.items()
    ]
    if settings.llm_provider == "openai":
        known.insert(0, ModelOut(id=settings.default_model, provider="openai"))
    return known
