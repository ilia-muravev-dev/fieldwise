"""Records model responses on disk and replays them, so CI can run the eval gate for free and a
prompt iteration can be re-scored without spending anything."""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from fieldwise.extraction.provider import LLMError, LLMProvider, LLMRequest, LLMResponse

CassetteMode = Literal["off", "record", "replay"]


def cassette_key(provider_name: str, request: LLMRequest) -> str:
    identity: dict[str, Any] = {
        "provider": provider_name,
        "model": request.model,
        "effort": request.effort,
        "max_tokens": request.max_tokens,
        "schema": hashlib.sha256(
            json.dumps(request.output_schema, sort_keys=True).encode()
        ).hexdigest()[:16],
        "system": hashlib.sha256(request.system.encode()).hexdigest()[:16],
        **request.cache_key,
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:32]


class CassetteProvider:
    def __init__(self, inner: LLMProvider, directory: Path, mode: CassetteMode) -> None:
        self.inner = inner
        self.directory = directory
        self.mode = mode
        self.name = inner.name
        self.hits = 0
        self.misses = 0

    def _path(self, request: LLMRequest) -> Path:
        return self.directory / f"{cassette_key(self.inner.name, request)}.json"

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self.mode == "off":
            return self.inner.complete(request)
        path = self._path(request)
        if path.exists():
            self.hits += 1
            return LLMResponse.from_dict(json.loads(path.read_text(encoding="utf-8"))["response"])
        if self.mode == "replay":
            self.misses += 1
            raise LLMError("cassette_miss", f"no recording at {path.name}", retryable=False)
        response = self.inner.complete(request)
        self.misses += 1
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"key": request.cache_key, "model": request.model, "response": response.to_dict()}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return response
