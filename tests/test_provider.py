# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenRouterProvider against the throwaway local server (the `server` fixture from conftest.py):
the chat request the design describes and its reply, the error messages, and the model
capabilities kept from /models."""

from __future__ import annotations

import base64

import pytest

from openrouter.provider import OpenRouterProvider

from slidemage.plugin_api import ProviderError

PNG = b"\x89PNG\r\n\x1a\nfake"
DATA_URI = "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_chat_sends_the_design_described_request_and_reads_the_reply(server):
    server.body = {"choices": [{"message": {"role": "assistant", "content": "answer"},
                                "finish_reason": "stop"}]}
    provider = OpenRouterProvider("deepseek/deepseek-chat", base_url=server.url, api_key="k-123")
    reply = provider.chat([{"role": "user", "content": "hi"}], system="be brief", images=[PNG],
                          schema={"type": "object"}, temperature=0.1, max_tokens=99, think=True, num_ctx=4096)
    request = server.requests[0]
    assert (request["method"], request["path"]) == ("POST", "/chat/completions")
    assert request["headers"]["authorization"] == "Bearer k-123"
    assert request["headers"]["http-referer"] == "https://slidemage.org"
    assert request["headers"]["x-title"] == "SlideMage"
    assert request["body"] == {
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": DATA_URI}},
            ]},
        ],
        "temperature": 0.1,
        "max_tokens": 99,
        "response_format": {"type": "json_schema", "json_schema": {"name": "response", "schema": {"type": "object"}}},
    }
    assert (reply.text, reply.truncated) == ("answer", False)


def test_a_refused_key_says_where_to_fix_it(server):
    provider = OpenRouterProvider("deepseek/deepseek-chat", base_url=server.url, api_key="k-123")
    server.status, server.body = 401, {"error": {"message": "No auth credentials found"}}
    with pytest.raises(ProviderError, match="refused the API key"):
        provider.chat([{"role": "user", "content": "a"}])


def test_models_keep_the_capabilities_the_server_reports(server):
    server.body = {"data": [
        {"id": "anthropic/claude-sonnet-4.5", "supported_parameters": ["tools", "temperature"],
         "architecture": {"input_modalities": ["text", "image"]}},
        {"id": "deepseek/deepseek-chat", "supported_parameters": ["temperature"],
         "architecture": {"input_modalities": ["text"]}},
    ]}
    provider = OpenRouterProvider(base_url=server.url, api_key="k-123")
    models = provider.models()
    assert [(model.id, model.supports_tools, model.sees_images) for model in models] == [
        ("anthropic/claude-sonnet-4.5", True, True),
        ("deepseek/deepseek-chat", False, False),
    ]
    assert provider.list_models() == ["anthropic/claude-sonnet-4.5", "deepseek/deepseek-chat"]
