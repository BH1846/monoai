"""Request Normalizer — pure parsing/validation, no routing/I/O. Converts
any of four wire formats (openai/anthropic/gemini/native) into one
RequestContext. Ported verbatim from
Lite_Multimodel_switching/monoai_router/hot_path/normalizer.py.
"""
from __future__ import annotations

from typing import Any

from router.contracts import ContentPart, Message, RequestContext


class NormalizationError(ValueError):
    """Raised when the payload cannot be parsed into a RequestContext."""


class RequestNormalizer:
    """Stateless; safe to share across requests."""

    def normalize(self, payload: dict[str, Any]) -> RequestContext:
        fmt = self._detect_format(payload)
        dispatch = {
            "openai": self._from_openai,
            "anthropic": self._from_anthropic,
            "gemini": self._from_gemini,
            "native": self._from_native,
        }
        return dispatch[fmt](payload)

    def _detect_format(self, payload: dict[str, Any]) -> str:
        if payload.get("format") == "monoai" or payload.get("_monoai") is True:
            return "native"
        if "contents" in payload:
            return "gemini"
        if isinstance(payload.get("system"), str):
            return "anthropic"
        if "messages" in payload:
            return "openai"
        raise NormalizationError(
            f"Cannot detect request format. Top-level keys found: {sorted(payload.keys())}"
        )

    def _from_openai(self, payload: dict[str, Any]) -> RequestContext:
        messages = [self._openai_message(m) for m in payload.get("messages", [])]
        return RequestContext(
            messages=messages,
            model_hint=payload.get("model"),
            max_tokens=payload.get("max_tokens"),
            tools=payload.get("tools"),
            stream=payload.get("stream", False),
            source_format="openai",
            temperature=payload.get("temperature"),
            extra=_strip(payload, {"messages", "model", "max_tokens", "tools", "stream", "temperature"}),
        )

    def _openai_message(self, m: dict[str, Any]) -> Message:
        raw_content = m["content"]
        if isinstance(raw_content, list):
            parts: list[ContentPart] = []
            for part in raw_content:
                if part["type"] == "text":
                    parts.append(ContentPart(type="text", text=part["text"]))
                elif part["type"] == "image_url":
                    url = part["image_url"]
                    if isinstance(url, dict):
                        url = url.get("url", "")
                    parts.append(ContentPart(type="image_url", image_url=url))
            return Message(role=m["role"], content=parts)
        return Message(role=m["role"], content=raw_content)

    def _from_anthropic(self, payload: dict[str, Any]) -> RequestContext:
        messages: list[Message] = []

        if system := payload.get("system"):
            messages.append(Message(role="system", content=system))

        for m in payload.get("messages", []):
            messages.append(self._anthropic_message(m))

        tools = None
        if ant_tools := payload.get("tools"):
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                }
                for t in ant_tools
            ]

        return RequestContext(
            messages=messages,
            model_hint=payload.get("model"),
            max_tokens=payload.get("max_tokens"),
            tools=tools,
            stream=payload.get("stream", False),
            source_format="anthropic",
            temperature=payload.get("temperature"),
            extra=_strip(payload, {"messages", "system", "model", "max_tokens", "tools", "stream", "temperature"}),
        )

    def _anthropic_message(self, m: dict[str, Any]) -> Message:
        raw_content = m["content"]
        if isinstance(raw_content, list):
            parts: list[ContentPart] = []
            for part in raw_content:
                if part["type"] == "text":
                    parts.append(ContentPart(type="text", text=part["text"]))
                elif part["type"] == "image":
                    src = part.get("source", {})
                    if src.get("type") == "base64":
                        parts.append(ContentPart(type="image_base64", image_data=src["data"]))
                    elif src.get("type") == "url":
                        parts.append(ContentPart(type="image_url", image_url=src["url"]))
            return Message(role=m["role"], content=parts)
        return Message(role=m["role"], content=raw_content)

    def _from_gemini(self, payload: dict[str, Any]) -> RequestContext:
        messages: list[Message] = []

        if sys_inst := payload.get("systemInstruction"):
            text = " ".join(p.get("text", "") for p in sys_inst.get("parts", []))
            if text:
                messages.insert(0, Message(role="system", content=text))

        for content in payload.get("contents", []):
            role = content.get("role", "user")
            if role == "model":
                role = "assistant"
            parts_raw = content.get("parts", [])
            if len(parts_raw) == 1 and "text" in parts_raw[0] and not any(
                k in parts_raw[0] for k in ("inline_data",)
            ):
                messages.append(Message(role=role, content=parts_raw[0]["text"]))
            else:
                parts: list[ContentPart] = []
                for p in parts_raw:
                    if "text" in p:
                        parts.append(ContentPart(type="text", text=p["text"]))
                    elif "inline_data" in p:
                        parts.append(ContentPart(type="image_base64", image_data=p["inline_data"]["data"]))
                messages.append(Message(role=role, content=parts))

        gen_cfg = payload.get("generationConfig", {})
        return RequestContext(
            messages=messages,
            model_hint=payload.get("model"),
            max_tokens=gen_cfg.get("maxOutputTokens"),
            tools=None,
            stream=payload.get("stream", False),
            source_format="gemini",
            temperature=gen_cfg.get("temperature"),
            extra=_strip(payload, {"contents", "model", "generationConfig", "stream", "systemInstruction"}),
        )

    def _from_native(self, payload: dict[str, Any]) -> RequestContext:
        messages: list[Message] = []
        for m in payload.get("messages", []):
            raw_content = m["content"]
            if isinstance(raw_content, list):
                parts = [ContentPart(**p) for p in raw_content]
                messages.append(
                    Message(role=m["role"], content=parts, tool_call_id=m.get("tool_call_id"), name=m.get("name"))
                )
            else:
                messages.append(
                    Message(role=m["role"], content=raw_content, tool_call_id=m.get("tool_call_id"), name=m.get("name"))
                )
        return RequestContext(
            messages=messages,
            model_hint=payload.get("model"),
            max_tokens=payload.get("max_tokens"),
            tools=payload.get("tools"),
            stream=payload.get("stream", False),
            source_format="native",
            temperature=payload.get("temperature"),
            extra=payload.get("extra", {}),
        )


def _strip(d: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k not in keys}
