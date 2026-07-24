"""Claude API backend with cost cap and content cache (spec §5.7).

  * Hard per-run cost cap: raises `CostCapExceeded` instead of a silent cost
    explosion. The pipeline catches it and returns a partial result.
  * Cache: identical prompt (by hash) is not re-sent — "identische Quelle mit
    gleichem Hash wird nicht neu extrahiert" (spec §5.7).
  * `.available` is False when no API key is configured; callers then use the
    deterministic offline path in roles.py.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import SETTINGS

# Rough public per-MTok prices (USD) for cost accounting only. Approximate on
# purpose — the point is a guardrail, not billing precision.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    # model_id: (input, output)
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}
_DEFAULT_PRICE = (3.0, 15.0)


class CostCapExceeded(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


@dataclass
class AnthropicBackend:
    """Thin wrapper around the Anthropic SDK for JSON completions."""

    cost_cap_usd: float = SETTINGS.run_cost_cap_usd
    cache_dir: Path = SETTINGS.llm_cache_dir
    usage: Usage = field(default_factory=Usage)
    _client: object | None = None

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if SETTINGS.llm_available:
            try:
                import anthropic  # noqa: PLC0415

                self._client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
            except Exception:  # pragma: no cover - SDK/env issues
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    @staticmethod
    def _price(model: str) -> tuple[float, float]:
        return _PRICE_PER_MTOK.get(model, _DEFAULT_PRICE)

    def _account(self, model: str, in_tok: int, out_tok: int) -> None:
        pin, pout = self._price(model)
        cost = in_tok / 1_000_000 * pin + out_tok / 1_000_000 * pout
        self.usage.input_tokens += in_tok
        self.usage.output_tokens += out_tok
        self.usage.cost_usd += cost
        self.usage.calls += 1
        if self.usage.cost_usd > self.cost_cap_usd:
            raise CostCapExceeded(
                f"run cost ${self.usage.cost_usd:.2f} exceeded cap "
                f"${self.cost_cap_usd:.2f}"
            )

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int = 1500,
    ) -> dict:
        """Return a parsed JSON object from the model.

        Uses a cached result when the (model, system, user) triple was seen
        before. Cache hits do not count against the cost cap.
        """
        if not self.available:
            raise RuntimeError("AnthropicBackend not available (no API key)")

        key = hashlib.sha256(
            f"{model}\x00{system}\x00{user}".encode("utf-8")
        ).hexdigest()[:32]
        cached = self._cache_path(key)
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))

        # We ask for raw JSON and parse defensively. (Structured-output tool use
        # would be a drop-in upgrade here.)
        msg = self._client.messages.create(  # type: ignore[union-attr]
            model=model,
            max_tokens=max_tokens,
            system=system + "\n\nReturn ONLY a single valid JSON object, no prose.",
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        self._account(model, msg.usage.input_tokens, msg.usage.output_tokens)

        data = _extract_json(text)
        cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object found in model output: {text[:200]!r}")
    return json.loads(text[start : end + 1])
