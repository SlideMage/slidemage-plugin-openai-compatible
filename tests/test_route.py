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
    route_id = Route("openrouter", CHAT, "deepseek/deepseek-chat")
    assert route.problem(ctx, route_id) == KEY_MESSAGE
    host.store.set("base_url", " http://localhost:11434/v1 ")
    assert route.problem(ctx, route_id) == ""
