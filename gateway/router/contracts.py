"""Data contracts shared between the normalizer, router, and provider
adapters. Ported verbatim from Lite_Multimodel_switching/monoai_router/contracts.py.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal, Union

from pydantic import BaseModel, Field


class ContentPart(BaseModel):
    """A single part inside a multi-part message (text or image)."""
    type: Literal["text", "image_url", "image_base64"]
    text: str | None = None
    image_url: str | None = None
    image_data: str | None = None


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Union[str, list[ContentPart]]
    tool_call_id: str | None = None
    name: str | None = None


class RequestContext(BaseModel):
    """Format-agnostic, normalized representation of any incoming request."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message]
    model_hint: str | None = None
    max_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None
    stream: bool = False
    source_format: Literal["openai", "anthropic", "gemini", "native"]
    temperature: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    request_id: str
    model_id: str
    provider: str
    content: str
    usage: dict[str, int]
    latency_ms: float
    difficulty: str | None = None
