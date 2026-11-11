# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenAI-compatible servers as a SlideMage AI route."""
from __future__ import annotations

from slidemage.plugin_api import Host

from .route import CompatibleRoute


def activate(host: Host) -> None:
    """Register without network, background work, or Qt widgets."""
    route = CompatibleRoute(host)
    host.add_ai_route(route)
    host.add_settings_section("ai", "OpenAI-compatible", route.build_settings_section)
