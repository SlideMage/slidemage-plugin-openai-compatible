# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings section against the fake host: the key is stored and the models refresh."""
from __future__ import annotations

import pytest

from fake_host import FakeHost
from openai_compatible.provider import CompatibleModel, CompatibleProvider, SERVERS
from openai_compatible.route import CompatibleRoute
from openai_compatible.tasks import CHAT
from slidemage.plugin_api import Route


@pytest.fixture(scope="module")
def qapp():
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        yield app


def test_saving_a_key_stores_it_and_refreshes_the_models(qapp, monkeypatch):
    from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton

    connections = []

    def models(provider):
        connections.append((provider.base_url, provider.api_key))
        return [CompatibleModel("m1")]

    monkeypatch.setattr(CompatibleProvider, "models", models)
    host = FakeHost()
    route = CompatibleRoute(host)
    page = route.build_settings_section()
    server = page.findChild(QComboBox)
    assert [server.itemText(i) for i in range(server.count())] == ["OpenAI", "Mistral", "OpenRouter", "Other"]
    url_field = next(e for e in page.findChildren(QLineEdit) if e.placeholderText().startswith("https://"))
    assert url_field.parentWidget().isHidden()
    key_field = next(e for e in page.findChildren(QLineEdit)
                     if e.echoMode() == QLineEdit.EchoMode.Password)
    save_key = next(b for b in page.findChildren(QPushButton) if b.text() == "Save key")
    changed = []
    page.changed.connect(lambda: changed.append(True))

    key_field.setText("openai-key")
    save_key.click()

    assert host.credentials_store.get(name="api.openai.com") == "openai-key"
    assert host.pending  # the model refresh for the new key is queued
    host.finish_next()
    assert host.changed_routes == ["openai-compatible"]
    assert changed

    key_field.setText("unsaved-openai-key")
    server.setCurrentText("Mistral")
    assert not key_field.text()
    assert host.store.saved["base_url"] == SERVERS["api.mistral.ai"][1]
    host.finish_next()
    assert connections[-1] == (SERVERS["api.mistral.ai"][1], "")
    key_field.setText("mistral-key")
    save_key.click()
    host.finish_next()
    assert connections[-1] == (SERVERS["api.mistral.ai"][1], "mistral-key")
    assert any("Mistral" in c.text() and SERVERS["api.mistral.ai"][2] in c.text() for c in page.findChildren(QLabel))

    server.setCurrentText("OpenAI")
    host.finish_next()
    assert connections[-1] == (SERVERS["api.openai.com"][1], "openai-key")
    server.setCurrentText("Other")
    assert not url_field.parentWidget().isHidden()
    host.finish_next()
    url_field.setText("http://localhost:1234/v1")
    url_field.editingFinished.emit()
    host.finish_next()
    assert connections[-1] == ("http://localhost:1234/v1", "")
    key_field.setText("local-key")
    save_key.click()
    host.finish_next()
    assert host.credentials_store.get(name="localhost") == "local-key"
    check = next(b for b in page.findChildren(QPushButton) if b.text() == "Check connection")
    check.click()
    host.finish_next()
    assert connections[-1] == ("http://localhost:1234/v1", "local-key")
    host.finish_next()
    assert route.model_choices(host.context(), CHAT) == ["m1"]
    assert route.provider(host.context(), Route(route.id, CHAT, "m1")).api_key == "local-key"
    save_key.click()  # an empty save clears only this server's key
    host.finish_next()
    assert host.credentials_store.get(name="localhost") is None
    assert host.credentials_store.get(name="api.openai.com") == "openai-key"
    assert host.credentials_store.get(name="api.mistral.ai") == "mistral-key"
    page.deleteLater()
