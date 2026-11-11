# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""CompatibleProvider against the throwaway local server (the `server` fixture from conftest.py):
the chat request the design describes and its reply, the error messages, and the model
capabilities kept from /models."""

from __future__ import annotations

import base64
import json

import pytest

from fake_http import sse_stream
from openai_compatible.provider import CompatibleProvider

from slidemage.plugin_api import AssistantMessage, ProviderError, ToolCall, ToolResult, ToolResultsMessage, ToolSpec, UserMessage

PNG = b"\x89PNG\r\n\x1a\nfake"
DATA_URI = "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_chat_sends_the_design_described_request_and_reads_the_reply(server):
    server.body = {"choices": [{"message": {"role": "assistant", "content": "answer"},
                                "finish_reason": "stop"}]}
    provider = CompatibleProvider("deepseek/deepseek-chat", base_url="https://openrouter.ai/api/v1/", api_key="k-123")
    reply = provider.chat([{"role": "user", "content": "hi"}], system="be brief", images=[PNG],
                          schema={"type": "object"}, temperature=0.1, max_tokens=99, think=True, num_ctx=4096)
    request = server.requests[0]
    assert (request["method"], request["path"]) == ("POST", "/api/v1/chat/completions")
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
    provider = CompatibleProvider("mistral-small-latest", base_url="https://api.mistral.ai/v1", api_key="k-123")
    server.status, server.body = 401, {"error": {"message": "No auth credentials found"}}
    with pytest.raises(ProviderError, match="Mistral refused the API key.*Settings → AI → OpenAI-compatible"):
        provider.chat([{"role": "user", "content": "a"}])


def test_models_keep_the_capabilities_the_server_reports(server):
    server.body = {"data": [
        {"id": "anthropic/claude-sonnet-4.5", "supported_parameters": ["tools", "temperature"],
         "architecture": {"input_modalities": ["text", "image"]}},
        {"id": "deepseek/deepseek-chat", "supported_parameters": ["temperature"],
         "architecture": {"input_modalities": ["text"]}},
        {"id": "unreported"},
    ]}
    provider = CompatibleProvider(base_url=server.url, api_key="k-123")
    models = provider.models()
    assert [(model.id, model.tools, model.images) for model in models] == [
        ("anthropic/claude-sonnet-4.5", True, True),
        ("deepseek/deepseek-chat", False, False),
        ("unreported", True, True),
    ]
    assert provider.list_models() == ["anthropic/claude-sonnet-4.5", "deepseek/deepseek-chat", "unreported"]


def test_a_streamed_turn_joins_text_and_split_tool_arguments(server):
    server.content_type = "text/event-stream"
    server.body = sse_stream(pieces=("Hello", [  # Mistral's reasoning models send a list of parts
        {"type": "thinking", "thinking": [{"type": "text", "text": "hmm"}]}, {"type": "text", "text": ", world"}]),
                             tool_calls=(("get_weather", ('{"city":', ' "Paris", ', '"unit": "c"}')),))
    provider = CompatibleProvider("deepseek/deepseek-chat", base_url=server.url, api_key="k-123")
    pieces: list[str] = []
    reply = provider.stream_turn(
        "be brief", [UserMessage("hi")],
        [ToolSpec(name="get_weather", description="The weather of a city", schema={"type": "object"})],
        pieces.append)
    request = server.requests[0]
    assert (request["method"], request["path"]) == ("POST", "/chat/completions")
    assert request["body"]["stream"] is True
    assert request["body"]["stream_options"] == {"include_usage": True}
    assert "http-referer" not in request["headers"]
    assert "x-title" not in request["headers"]
    assert reply.text == "Hello, world"
    assert pieces == ["Hello", ", world"]
    assert [(call.id, call.name, call.input) for call in reply.tool_calls] == [
        ("call_0", "get_weather", {"city": "Paris", "unit": "c"})]
    assert (reply.stop, reply.usage) == ("tool_use", {"input": 12, "output": 5})


def test_tool_results_and_their_images_go_out_after_the_call(server):
    server.content_type = "text/event-stream"
    server.body = sse_stream()
    provider = CompatibleProvider("deepseek/deepseek-chat", base_url=server.url, api_key="k-123")
    reply = provider.stream_turn(
        "be brief", [
            UserMessage("hi"),
            AssistantMessage(tool_calls=[ToolCall("call_0", "get_weather", {"city": "Paris"})]),
            ToolResultsMessage([ToolResult("call_0", "15 C", images=[PNG])]),
        ], [], lambda _text: None)
    assert server.requests[0]["body"]["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_0", "type": "function",
             "function": {"name": "get_weather", "arguments": json.dumps({"city": "Paris"})}}]},
        {"role": "tool", "tool_call_id": "call_0", "content": "15 C"},
        {"role": "user", "content": [
            {"type": "text", "text": "The image from the tool above:"},
            {"type": "image_url", "image_url": {"url": DATA_URI}}]},
    ]
    assert (reply.text, reply.stop) == ("", "end_turn")


def test_openai_uses_completion_tokens_without_temperature(server):
    provider = CompatibleProvider("o3", base_url="https://api.openai.com/v1/", api_key="openai-key")
    server.body = {"choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}]}
    assert provider.chat([{"role": "user", "content": "hi"}], temperature=0.1, max_tokens=99).text == "answer"
    server.body = sse_stream(pieces=("answer",))
    assert provider.stream_turn("", [UserMessage("hi")], [], lambda _: None, max_tokens=99).text == "answer"
    assert provider.service == "OpenAI"
    for request in server.requests:
        assert request["path"] == "/v1/chat/completions"
        assert request["body"]["max_completion_tokens"] == 99
        assert "max_tokens" not in request["body"]
        assert "temperature" not in request["body"]
        assert request["headers"]["authorization"] == "Bearer openai-key"
        assert "http-referer" not in request["headers"]
        assert "x-title" not in request["headers"]


def test_mistral_capabilities_and_tool_image_bridge(server):
    provider = CompatibleProvider("mistral-small-latest", base_url="https://api.mistral.ai/v1/")
    server.body = {"data": [
        {"id": "vision", "capabilities": {"function_calling": True, "vision": True}},
        {"id": "text", "capabilities": {"function_calling": True, "vision": False}},
        {"id": "embedding", "capabilities": {"function_calling": False, "vision": False}},
    ]}
    assert [(m.id, m.tools, m.images) for m in provider.models()] == [
        ("vision", True, True), ("text", True, False), ("embedding", False, False)]
    server.body = sse_stream(pieces=("I see it.",))
    reply = provider.stream_turn("", [
        UserMessage("Show me the slide."),
        AssistantMessage(tool_calls=[ToolCall("imagecall", "render", {})]),
        ToolResultsMessage([ToolResult("imagecall", "slide", images=[PNG])]),
    ], [], lambda _: None)
    request = server.requests[-1]
    assert "stream_options" not in request["body"]
    assert request["body"]["max_tokens"] == 16000
    assert [m["role"] for m in request["body"]["messages"]] == ["user", "assistant", "tool", "assistant", "user"]
    assert request["body"]["messages"][-2]["content"]
    assert request["body"]["messages"][-1]["content"][-1] == {"type": "image_url", "image_url": {"url": DATA_URI}}
    assert (reply.text, reply.usage) == ("I see it.", {"input": 12, "output": 5})
