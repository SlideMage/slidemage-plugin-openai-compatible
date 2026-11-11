# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""The OpenRouter settings page (Step 4 writes the fields)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from slidemage.plugin_api import Host, Widget


def build(host: Host, route: Any) -> Widget:
    """A stub page until Step 4 adds base URL, key, extra model IDs and connection check."""
    return host.Page()
