# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""The route's problem messages: a key unless the server is on this computer."""
from __future__ import annotations

from fake_host import FakeHost
from openai_compatible.route import KEY_MESSAGE, CompatibleRoute
from openai_compatible.tasks import CHAT
from slidemage.plugin_api import Route


def test_a_key_is_needed_unless_the_server_is_local():
    host = FakeHost()
    route = CompatibleRoute(host)
    ctx = host.context()
    route_id = Route("openai-compatible", CHAT, "a-model")
    assert route.problem(ctx, route_id) == KEY_MESSAGE
    assert route.service == "OpenAI"
    assert route.default_choice(CHAT) == ""
    host.credentials_store.set("openai-key", name="api.openai.com")
    assert route.problem(ctx, route_id) == ""
    assert route.provider(ctx, route_id).api_key == "openai-key"
    host.store.set("base_url", "https://api.mistral.ai/v1")
    assert route.service == "Mistral"
    assert route.problem(ctx, route_id) == KEY_MESSAGE
    assert route.provider(ctx, route_id).api_key == ""
    assert route.work_label(route_id) == "a-model · Mistral"
    host.store.set("base_url", "https://openrouter.ai/api/v1/")
    assert route.service == "OpenRouter"
    assert route.default_choice(CHAT) == "openrouter/auto"
    host.credentials_store.set("router-key", name="openrouter.ai")
    assert route.problem(ctx, route_id) == ""
    host.store.set("base_url", " http://localhost:11434/v1 ")
    assert route.service == "localhost"
    assert route.default_choice(CHAT) == ""
    assert route.problem(ctx, route_id) == ""
