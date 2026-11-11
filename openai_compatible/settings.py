# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""Server, API key, extra model IDs and connection check."""
from __future__ import annotations


from slidemage.plugin_api import Host, Widget

from .provider import DEFAULT_BASE_URL, SERVERS, CompatibleProvider, host_of, server_name
from .route import CompatibleRoute, _base_url


def build(host: Host, route: CompatibleRoute) -> Widget:
    """Settings → AI → OpenAI-compatible; built only when Settings opens."""
    from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton

    page = host.Page()
    settings = host.settings()

    server = QComboBox()
    for name, address, _key_page in SERVERS.values():
        server.addItem(name, address)
    server.addItem("Other", "")
    selected = server.findData(_base_url(host).rstrip("/"))
    server.setCurrentIndex(selected if selected >= 0 else server.count() - 1)
    page.body.addWidget(host.Field("Server", server))

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

    url_field = text_setting("base_url", "Base URL", DEFAULT_BASE_URL, lambda: server_changed(False))
    url_field.setText(_base_url(host))
    url_field.parentWidget().setVisible(not server.currentData())

    key_field = QLineEdit()
    key_field.setEchoMode(QLineEdit.EchoMode.Password)
    key_field.setPlaceholderText("API key for the selected server")
    url_field.textChanged.connect(lambda _text: key_field.clear())
    key_note = host.caption("")

    def key_note_text() -> str:
        address = _base_url(host)
        hostname = host_of(address)
        where = route.credentials.where(name=hostname)
        storage = f"Key saved in the {where}." if where else "No key yet. Stored on this computer (keychain or a private file)."
        key_page = f" Get a key: {SERVERS[hostname][2]}." if hostname in SERVERS else ""
        return f"{storage} Sent to {server_name(address)} ({address}).{key_page}"

    key_note.setText(key_note_text())

    def save_key() -> None:
        try:
            hostname = host_of(_base_url(host))
            if key_field.text():
                route.credentials.set(key_field.text(), name=hostname)
            else:
                route.credentials.clear(name=hostname)
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

    def server_changed(choose: bool = True) -> None:
        if choose:
            address = server.currentData() or url_field.text().strip()
            url_field.setText(address)
            settings.set("base_url", address)
            settings.save()
        url_field.parentWidget().setVisible(not server.currentData())
        key_field.clear()  # typed keys belong to the server shown when they were entered
        key_note.setText(key_note_text())
        status.clear()
        check.setEnabled(True)
        route.refresh_models()
        if choose:
            page.changed.emit()

    server.currentIndexChanged.connect(lambda _index: server_changed())

    def check_connection() -> None:
        # The key field stays empty when a key is stored, so an empty field means the stored one.
        address = url_field.text().strip() or DEFAULT_BASE_URL
        provider = CompatibleProvider(base_url=address,
                                      api_key=key_field.text() or route.credentials.get(name=host_of(address)) or "")
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
