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
import urllib.parse
from dataclasses import dataclass

from slidemage.plugin_api import ChatReply, ProviderError

from .http import HttpProvider

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

    def __init__(self, model: str = "", base_url: str = DEFAULT_BASE_URL, api_key: str = "") -> None:
        super().__init__()
        self.model = model
        self.base_url = base_url or DEFAULT_BASE_URL
        self.api_key = api_key

    @property
    def label(self) -> str:
        return self.model

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
        host = urllib.parse.urlsplit(self.base_url).hostname or self.base_url
        return f"{host} returned HTTP {status}: {detail}"

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


def _data_uri(image: bytes) -> str:
    return f"data:{_image_media_type(image)};base64,{base64.b64encode(image).decode()}"


def _image_media_type(data: bytes) -> str:
    for magic, media_type in ((b"\x89PNG", "image/png"), (b"\xff\xd8", "image/jpeg"), (b"GIF8", "image/gif")):
        if data.startswith(magic):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ProviderError("Only PNG, JPEG, GIF and WebP images can be sent.")
