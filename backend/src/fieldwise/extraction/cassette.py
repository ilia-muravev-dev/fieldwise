"""Records model responses on disk and replays them, so CI can run the eval gate for free and a
prompt iteration can be re-scored without spending anything."""

import hashlib
import json
from collections.abc import Callable
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

    def _load(self, request: LLMRequest) -> LLMResponse | None:
        path = self._path(request)
        if not path.exists():
            return None
        self.hits += 1
        return LLMResponse.from_dict(json.loads(path.read_text(encoding="utf-8"))["response"])

    def _save(self, request: LLMRequest, response: LLMResponse) -> None:
        if response.truncated:
            return  # a cut-off answer is worth retrying, not replaying
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"key": request.cache_key, "model": request.model, "response": response.to_dict()}
        self._path(request).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self.mode == "off":
            return self.inner.complete(request)
        cached = self._load(request)
        if cached is not None:
            return cached
        self.misses += 1
        if self.mode == "replay":
            raise LLMError(
                "cassette_miss", f"no recording for {request.cache_key}", retryable=False
            )
        response = self.inner.complete(request)
        self._save(request, response)
        return response

    def estimate_input_tokens(self, request: LLMRequest) -> int | None:
        estimate = getattr(self.inner, "estimate_input_tokens", None)
        return estimate(request) if estimate else None

    def complete_batch(
        self, requests: list[LLMRequest], *, on_status: Callable[[str, int], None] | None = None
    ) -> list[LLMResponse | LLMError]:
        """Serves recorded requests from disk and sends only the rest to the inner batch."""
        inner_batch = getattr(self.inner, "complete_batch", None)
        outcomes: list[LLMResponse | LLMError | None] = [None] * len(requests)
        pending: list[int] = []
        for index, request in enumerate(requests):
            cached = self._load(request) if self.mode != "off" else None
            if cached is not None:
                outcomes[index] = cached
            elif self.mode == "replay":
                self.misses += 1
                outcomes[index] = LLMError(
                    "cassette_miss", f"no recording for {request.cache_key}", retryable=False
                )
            else:
                pending.append(index)
        if pending:
            if inner_batch is None:
                raise LLMError("bad_request", f"{self.inner.name} cannot batch", retryable=False)
            fresh = inner_batch([requests[i] for i in pending], on_status=on_status)
            for index, outcome in zip(pending, fresh, strict=True):
                outcomes[index] = outcome
                if isinstance(outcome, LLMResponse) and self.mode == "record":
                    self._save(requests[index], outcome)
                    self.misses += 1
        return [
            o if o is not None else LLMError("server", "lost", retryable=True) for o in outcomes
        ]
