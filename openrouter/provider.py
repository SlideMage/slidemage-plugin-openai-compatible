# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""The OpenRouter provider, and any OpenAI-compatible /chat/completions server.

One API key for OpenRouter's catalogue; with another base URL, any server that
speaks the OpenAI chat wire format on it. A provider is bound to one model;
callers hold prompts and result checks, never HTTP. The abortable HTTP plumbing
is local (see http.py); the neutral types come from the public API. `think` and
`num_ctx` are accepted and ignored: they are Ollama's options, and reasoning
models on OpenRouter decide for themselves when to reason.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from slidemage.plugin_api import (
    AgentMessage, AssistantMessage, Cancelled, ChatReply, ProviderError, ToolCall, ToolResultsMessage, ToolSpec,
)

from .http import HttpProvider, error_detail

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
SLIDEMAGE_URL = "https://slidemage.org"

Message = dict[str, str]


@dataclass
class OpenRouterModel:
    """One model from /models, with the capabilities OpenRouter reports about it."""

    id: str
    supported_parameters: tuple[str, ...] = ()
    input_modalities: tuple[str, ...] = ()

    @property
    def supports_tools(self) -> bool:
        return "tools" in self.supported_parameters

    @property
    def sees_images(self) -> bool:
        return "image" in self.input_modalities


class OpenRouterProvider(HttpProvider):
    """A model on OpenRouter, or on another OpenAI-compatible server."""

    service = "OpenRouter"
    is_local = False

    def __init__(self, model: str = "", base_url: str = DEFAULT_BASE_URL, api_key: str = "",
                 sees_images: bool = True) -> None:
        super().__init__()
        self.model = model
        self.base_url = base_url or DEFAULT_BASE_URL
        self.api_key = api_key
        self.sees_images = sees_images

    @property
    def label(self) -> str:
        return self.model

    @property
    def host(self) -> str:
        return urllib.parse.urlsplit(self.base_url).hostname or self.base_url

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "HTTP-Referer": SLIDEMAGE_URL, "X-Title": "SlideMage"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _describe_error(self, status: int, detail: str) -> str:
        if status in (401, 403):
            return "The server refused the API key. Check it under Settings → AI → OpenRouter."
        if status == 404 and self.model:
            return f"The server has no model '{self.model}'. Choose another model in AI setup."
        return f"{self.host} returned HTTP {status}: {detail}"

    def chat(
        self, messages: list[Message], *, system: str = "",
        images: list[bytes] | None = None, schema: dict | None = None,
        temperature: float = 0.2, max_tokens: int = 2048, timeout: float = 300.0,
        think: bool = False, num_ctx: int | None = None,
    ) -> ChatReply:
        turns: list[dict] = []
        if system:
            turns.append({"role": "system", "content": system})
        turns += [dict(m) for m in messages]
        if images:
            parts = [{"type": "text", "text": turns[-1].get("content", "")}]
            parts += [{"type": "image_url", "image_url": {"url": _data_uri(image)}} for image in images]
            turns[-1] = {**turns[-1], "content": parts}
        payload: dict = {
            "model": self.model,
            "messages": turns,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "response", "schema": schema}}
        status, raw = self._send("POST", self.base_url, "/chat/completions", headers=self._headers(),
                                 payload=payload, timeout=timeout)
        body = self._json(status, raw, self._describe_error)
        choice = (body.get("choices") or [{}])[0]
        return ChatReply(
            text=(choice.get("message") or {}).get("content") or "",
            truncated=choice.get("finish_reason") == "length",
        )

    def models(self) -> list[OpenRouterModel]:
        """The server's models, with the capabilities it reports about each. Raises ProviderError."""
        status, raw = self._send("GET", self.base_url, "/models", headers=self._headers(), payload=None, timeout=10)
        body = self._json(status, raw, self._describe_error)
        return [
            OpenRouterModel(
                id=entry["id"],
                supported_parameters=tuple(entry.get("supported_parameters") or ()),
                input_modalities=tuple((entry.get("architecture") or {}).get("input_modalities") or ()),
            )
            for entry in body.get("data") or ()
            if entry.get("id")
        ]

    def list_models(self) -> list[str]:
        """The model ids to offer; [] when the server cannot be asked."""
        try:
            return [model.id for model in self.models()]
        except ProviderError:
            return []

    def stream_turn(
        self, system: str, messages: list[AgentMessage], tools: list[ToolSpec],
        on_text: Callable[[str], None], *, max_tokens: int = 16000, timeout: float = 300.0,
    ) -> AssistantMessage:
        """One agent turn: /chat/completions streamed as SSE, text deltas to `on_text`, the tool
        calls' argument pieces joined and parsed once at the end."""
        payload: dict = {
            "model": self.model,
            "messages": _wire_messages(system, messages, self.sees_images),
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": tool.name, "description": tool.description, "parameters": tool.schema,
            }} for tool in tools]
        text: list[str] = []
        calls: dict[int, dict] = {}     # tool call pieces by their stream index
        usage: dict = {}
        finish_reason = ""
        saw_done = False
        with self._request("POST", self.base_url, "/chat/completions", headers=self._headers(),
                           payload=payload, timeout=timeout) as response:
            if response.status != 200:
                raise ProviderError(self._describe_error(response.status, error_detail(response.read())))
            for line in response:
                if self._cancelled:
                    raise Cancelled("Aborted.")
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                if data == b"[DONE]":
                    saw_done = True
                    break
                try:
                    event = json.loads(data)
                except ValueError as exc:
                    raise ProviderError(f"{self.host} sent an unreadable response: {exc}") from exc
                if not isinstance(event, dict):
                    continue
                choice = (event.get("choices") or [{}])[0]
                if event.get("error"):
                    error = event["error"]
                    message = error.get("message") if isinstance(error, dict) else str(error)
                    raise ProviderError(f"{self.host} returned an error: {message}")
                delta = choice.get("delta") or {}
                for part in (delta.get("content"), delta.get("refusal")):
                    if part:
                        text.append(part)
                        on_text(part)
                for entry in delta.get("tool_calls") or ():
                    call = calls.setdefault(entry.get("index", 0), {"id": "", "name": "", "arguments": ""})
                    if entry.get("id"):
                        call["id"] = entry["id"]
                    if not call["id"]:
                        call["id"] = f"call_{uuid.uuid4().hex[:12]}"
                    if entry.get("function", {}).get("name"):
                        call["name"] = entry["function"]["name"]
                    if entry.get("function", {}).get("arguments"):
                        call["arguments"] += entry["function"]["arguments"]
                if event.get("usage"):
                    usage = event["usage"]
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
        if self._cancelled:
            raise Cancelled("Aborted.")
        if not finish_reason and not saw_done:
            raise ProviderError(f"{self.host} ended the answer early.")
        return AssistantMessage(
            text="".join(text),
            tool_calls=[ToolCall(call["id"], call["name"], _parsed_arguments(call["arguments"]))
                        for _, call in sorted(calls.items())],
            stop="max_tokens" if finish_reason == "length"
                 else "refusal" if finish_reason == "content_filter"
                 else "tool_use" if calls else "end_turn",
            usage={"input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0)},
        )


def _wire_messages(system: str, messages: list[AgentMessage], sees_images: bool) -> list[dict]:
    """The agent's neutral history as OpenAI chat messages: the tool calls as the wire's
    assistant tool_calls, each tool result as a "tool" message, and everything a
    ToolResultsMessage carries as images in one user message after its last tool message.
    For a model that cannot see images, no image parts go on the wire and each tool
    result that had images says so in its text."""
    wire: list[dict] = [{"role": "system", "content": system}] if system else []
    for message in messages:
        if isinstance(message, AssistantMessage):
            turn = {"role": "assistant", "content": message.text}
            if message.tool_calls:
                turn["tool_calls"] = [{"id": call.id, "type": "function", "function": {
                    "name": call.name, "arguments": json.dumps(call.input),
                }} for call in message.tool_calls]
            wire.append(turn)
        elif isinstance(message, ToolResultsMessage):
            images: list[bytes] = []
            for result in message.results:
                text = ("Error: " if result.is_error else "") + result.text
                if result.images and not sees_images:
                    text += "\n(An image was rendered, but this model cannot look at images.)"
                wire.append({"role": "tool", "tool_call_id": result.call_id, "content": text})
                if sees_images:
                    images += result.images
            if images:
                wire.append({"role": "user", "content": [{"type": "text", "text": "The image from the tool above:"}] + [
                    {"type": "image_url", "image_url": {"url": _data_uri(image)}} for image in images]})
        else:
            wire.append({"role": "user", "content": message.text})
    return wire


def _parsed_arguments(arguments: str) -> dict:
    """A streamed tool call's arguments string as a dict, {} when it does not parse."""
    try:
        parsed = json.loads(arguments or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _data_uri(image: bytes) -> str:
    return f"data:{_image_media_type(image)};base64,{base64.b64encode(image).decode()}"


def _image_media_type(data: bytes) -> str:
    for magic, media_type in ((b"\x89PNG", "image/png"), (b"\xff\xd8", "image/jpeg"), (b"GIF8", "image/gif")):
        if data.startswith(magic):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ProviderError("Only PNG, JPEG, GIF and WebP images can be sent.")
