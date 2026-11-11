# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""The fixtures the plugin's tests share."""
import pytest
from urllib.parse import urlsplit

from openai_compatible.http import HttpProvider


@pytest.fixture
def server(monkeypatch):
    """Keep the requested server host, but send all HTTP through the local fake."""
    from fake_http import Server

    try:
        srv = Server()
    except PermissionError:
        # Keep exercising HTTP serialization and abort signalling when the
        # runner forbids sockets. Normal CI still tests real loopback TCP.
        srv = Server(in_memory=True)
        monkeypatch.setattr(HttpProvider, "_connection", staticmethod(srv.connection))
    connection = HttpProvider()._connection
    monkeypatch.setattr(HttpProvider, "_connection", lambda self, parts, timeout: connection(urlsplit(srv.url), timeout))
    yield srv
    srv.close()
