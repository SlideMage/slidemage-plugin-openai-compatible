# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""The OpenRouter settings section: base URL, API key, extra model IDs, connection check."""
from __future__ import annotations

from slidemage.plugin_api import Host, Widget

from .provider import DEFAULT_BASE_URL, OpenRouterProvider
from .route import OpenRouterRoute


def build(host: Host, route: OpenRouterRoute) -> Widget:
    """Settings → AI → OpenRouter; built only when the Settings sheet opens."""
    from PySide6.QtWidgets import QLineEdit, QPushButton

    page = host.Page()
    settings = host.settings()

    def text_setting(key: str, label: str, placeholder: str, after_save) -> QLineEdit:
        """A line edit for one string setting, saved when editing finishes and the text changed."""
        field = QLineEdit()
        saved = settings.get(key)
        field.setText(saved if isinstance(saved, str) else "")
        field.setPlaceholderText(placeholder)

        def save() -> None:
            text, saved = field.text().strip(), settings.get(key)
            if text == (saved if isinstance(saved, str) else ""):
                return
            settings.set(key, text)
            settings.save()
            after_save()
            page.changed.emit()

        field.editingFinished.connect(save)
        page.body.addWidget(host.Field(label, field))
        return field

    url_field = text_setting("base_url", "Base URL", DEFAULT_BASE_URL, route.refresh_models)

    key_field = QLineEdit()
    key_field.setEchoMode(QLineEdit.EchoMode.Password)
    key_field.setPlaceholderText("API key from openrouter.ai/keys")
    key_note = host.caption("")

    def key_note_text() -> str:
        where = route.credentials.where()
        if where:
            return f"Key saved in the {where}. Sent to the base URL above."
        return "No key yet. It will be stored on this computer (keychain or a private file) and sent to the base URL above."

    key_note.setText(key_note_text())

    def save_key() -> None:
        try:
            route.credentials.set(key_field.text())
        except OSError as exc:
            key_note.setText(f"Could not save the key: {exc}")
            return
        key_field.clear()
        key_note.setText(key_note_text())
        route.refresh_models()
        page.changed.emit()

    save_key_button = QPushButton("Save key")
    save_key_button.clicked.connect(save_key)
    page.body.addWidget(host.Field("API key", key_field))
    page.body.addWidget(key_note)
    page.body.addWidget(save_key_button)

    text_setting("extra_models", "Extra model IDs", "optional: model-id, another-model-id",
                 lambda: host.model_choices_changed(route.id))

    status = host.caption("")
    check = QPushButton("Check connection")
    closed = [False]
    page.destroyed.connect(lambda: closed.__setitem__(0, True))

    def check_connection() -> None:
        # The key field stays empty when a key is stored, so an empty field means the stored one.
        provider = OpenRouterProvider(base_url=url_field.text().strip() or DEFAULT_BASE_URL,
                                      api_key=key_field.text() or route.credentials.get() or "")
        status.setText("Checking connection…")
        check.setEnabled(False)

        def done(models: list | None, error: BaseException | None) -> None:
            if closed[0]:
                return
            check.setEnabled(True)
            if error is not None:
                status.setText(str(error))
                return
            count = len(models)
            status.setText(f"Connected: {count} model{'s' if count != 1 else ''}.")
            route.refresh_models()  # heals a model list that failed before (server not running at start)

        host.run_in_background(provider.models, done)

    check.clicked.connect(check_connection)
    page.body.addWidget(check)
    page.body.addWidget(status)
    return page
