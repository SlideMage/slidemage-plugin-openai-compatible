# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenRouter's public AI route and asynchronous model cache."""
from __future__ import annotations

from urllib.parse import urlsplit
from typing import Any

from slidemage.plugin_api import Host, Route, RouteContext, Widget

from .tasks import CHAT, IMAGE_DESCRIPTION, TASKS, TASK_LABELS
from .provider import DEFAULT_BASE_URL, CompatibleModel, CompatibleProvider

KEY_MESSAGE = "Add an API key under Settings → AI → OpenRouter."


# The route reads the plugin's own settings through the host: RouteContext.settings is the same store.
def _base_url(host: Host) -> str:
    saved = host.settings().get("base_url")
    return (saved.strip() if isinstance(saved, str) else "") or DEFAULT_BASE_URL


def _extra_models(host: Host) -> list[str]:
    """The model ids the user entered under Extra model IDs, spelled out."""
    raw = host.settings().get("extra_models")
    if not isinstance(raw, str):
        return []
    return [model.strip() for model in raw.split(",") if model.strip()]


def _is_local(address: str) -> bool:
    host = urlsplit(address).hostname or ""
    return host == "localhost" or host.startswith("127.") or host == "::1"


class CompatibleRoute:
    id = "openrouter"
    service = "OpenRouter"
    is_local = False
    tasks = frozenset(TASKS)

    def __init__(self, host: Host) -> None:
        self.host = host
        self.credentials = host.credentials()
        self._models: list[CompatibleModel] = []
        self._models_at: str | None = None
        self._loading_at: str | None = None
        self._generation = 0

    def problem(self, ctx: RouteContext, route: Route) -> str:
        if not route.model:
            return (f"Choose an OpenRouter model for {TASK_LABELS[route.task].lower()} "
                    "under AI setup (the ▾ of the AI switch).")
        if not self.credentials.get() and not _is_local(_base_url(self.host)):
            return KEY_MESSAGE
        return ""

    def default_choice(self, task: str) -> str:
        return ""

    def choice_label(self, choice: str) -> str:
        return choice

    def split_choice(self, choice: str) -> tuple[str, str | None]:
        return choice, None

    def valid_choice(self, ctx: RouteContext, choice: str) -> bool:
        return bool(choice)

    def work_label(self, route: Route) -> str:
        address = _base_url(self.host)
        return f"{route.model or 'no model chosen'} · {urlsplit(address).hostname or address}"

    def model_choices(self, ctx: RouteContext, task: str) -> list[str]:
        """Return at once. Only refresh_models' worker contacts the server."""
        address = _base_url(self.host)
        if self._models_at != address and self._loading_at != address:
            self.refresh_models()
        cached = self._models if self._models_at == address else []
        offered = [model.id for model in cached
                   if (task != CHAT or model.tools) and (task != IMAGE_DESCRIPTION or model.images)]
        return list(dict.fromkeys(_extra_models(self.host) + offered))

    def refresh_models(self) -> None:
        """Refresh the cache off-thread; a newer request supersedes an older one."""
        address = _base_url(self.host)
        provider = CompatibleProvider(base_url=address, api_key=self.credentials.get() or "")
        self._generation += 1
        generation = self._generation
        self._loading_at = address

        def finished(models: list[CompatibleModel] | None, error: BaseException | None) -> None:
            if generation != self._generation:
                return
            self._loading_at = None
            self._models_at = address
            self._models = list(models or [])
            if error is not None:
                self.host.log(f"Could not list the models: {error}")
            self.host.model_choices_changed(self.id)

        self.host.run_in_background(provider.models, finished)

    def provider(self, ctx: RouteContext, route: Route) -> CompatibleProvider:
        """Capture the settings and key now; later ones apply to the next provider."""
        address = _base_url(self.host)
        cached = self._models if self._models_at == address else []
        known = next((model for model in cached if model.id == route.model), None)
        return CompatibleProvider(route.model, address, self.credentials.get() or "",
                                  sees_images=known.images if known else True)

    def draft_backend(self, ctx: RouteContext, route: Route, cancel: Any = None) -> None:
        return None  # core's image backend wraps provider()

    def translation_backend(self, ctx: RouteContext, route: Route, cancel: Any = None) -> None:
        return None  # core's translation backend wraps provider()

    def slide_translator(self, ctx: RouteContext, route: Route) -> None:
        return None  # core wraps provider()

    def task_runner(self, ctx: RouteContext, route: Route) -> None:
        return None  # core's provider_tasks

    def chat_surface(self, *args: Any, **kwargs: Any) -> None:
        return None  # core's provider chat view

    def settings_section(self) -> None:
        # Registered through Host.add_settings_section, so core must not build it twice.
        return None

    def build_settings_section(self) -> Widget:
        from . import settings  # Qt only when Settings opens

        return settings.build(self.host, self)
