# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenRouter, and any OpenAI-compatible server, as a SlideMage AI route."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slidemage.plugin_api import Host


def activate(host: Host) -> None:
    """Register without network, background work, or Qt widgets (route and settings come in later steps)."""
