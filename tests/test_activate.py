# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""Activation registers the route and the AI settings section."""
from __future__ import annotations

from fake_host import FakeHost
from openai_compatible import activate
from openai_compatible.tasks import TASKS


def test_activate_registers_one_route_and_one_ai_settings_section():
    host = FakeHost()
    activate(host)
    host.finish_activation()
    route, = host.routes.values()
    section, = host.sections
    assert (route.id, route.service, route.is_local, route.tasks) == (
        "openrouter", "OpenRouter", False, frozenset(TASKS))
    assert (section.page, section.title) == ("ai", "OpenRouter")
    assert section.build == route.build_settings_section
