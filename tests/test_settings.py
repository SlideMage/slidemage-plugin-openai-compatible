# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""The settings section against the fake host: the key is stored and the models refresh."""
from __future__ import annotations

import pytest

from fake_host import FakeHost
from openai_compatible.provider import CompatibleModel, CompatibleProvider
from openai_compatible.route import CompatibleRoute


@pytest.fixture(scope="module")
def qapp():
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        yield app


def test_saving_a_key_stores_it_and_refreshes_the_models(qapp, monkeypatch):
    from PySide6.QtWidgets import QLineEdit, QPushButton

    monkeypatch.setattr(CompatibleProvider, "models", lambda self: [CompatibleModel("m1")])
    host = FakeHost()
    page = CompatibleRoute(host).build_settings_section()
    key_field = next(e for e in page.findChildren(QLineEdit)
                     if e.echoMode() == QLineEdit.EchoMode.Password)
    save_key = next(b for b in page.findChildren(QPushButton) if b.text() == "Save key")
    changed = []
    page.changed.connect(lambda: changed.append(True))

    key_field.setText("sk-or-test")
    save_key.click()

    assert host.credentials_store.get() == "sk-or-test"
    assert host.pending  # the model refresh for the new key is queued
    host.finish_next()
    assert host.changed_routes == ["openrouter"]
    assert changed
    page.deleteLater()
