from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Usage:
    """Real per-call token usage as reported by the model API."""

    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0


