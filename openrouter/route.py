# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenRouter's public AI route and asynchronous model cache."""
from __future__ import annotations

from urllib.parse import urlsplit
from typing import Any

from slidemage.plugin_api import Host, Route, RouteContext, Widget

from .tasks import CHAT, IMAGE_DESCRIPTION, TASKS, TASK_LABELS
from .provider import DEFAULT_BASE_URL, OpenRouterModel, OpenRouterProvider

KEY_MESSAGE = "Add an API key under Settings → AI → OpenRouter."


def _settings(source: Host | RouteContext):
    """The settings store a source holds (Host has a method, RouteContext a value)."""
    return source.settings() if callable(source.settings) else source.settings


def _base_url(source: Host | RouteContext) -> str:
    saved = _settings(source).get("base_url")
    return (saved.strip() if isinstance(saved, str) else "") or DEFAULT_BASE_URL


def _extra_models(source: Host | RouteContext) -> list[str]:
    """The model ids the user entered under Extra model IDs, spelled out."""
    raw = _settings(source).get("extra_models")
    if not isinstance(raw, str):
        return []
    return [model.strip() for model in raw.split(",") if model.strip()]


def _is_local(address: str) -> bool:
    host = urlsplit(address).hostname or ""
    return host == "localhost" or host.startswith("127.") or host == "::1"


def _offering(task: str, models: list[OpenRouterModel]) -> list[str]:
    """The server's model ids that can do `task`; the filters apply only where the
    server reported capabilities, so an unreporting server offers every model."""
    return [model.id for model in models
            if (task != CHAT or not model.supported_parameters or model.supports_tools)
            and (task != IMAGE_DESCRIPTION or not model.input_modalities or model.sees_images)]


class OpenRouterRoute:
    id = "openrouter"
    service = "OpenRouter"
    is_local = False
    tasks = frozenset(TASKS)

    def __init__(self, host: Host) -> None:
        self.host = host
        self.credentials = host.credentials()
        self._models: list[OpenRouterModel] = []
        self._models_at: str | None = None
        self._loading_at: str | None = None
        self._generation = 0

    def problem(self, ctx: RouteContext, route: Route) -> str:
        if not route.model:
            return (f"Choose an OpenRouter model for {TASK_LABELS[route.task].lower()} "
                    "under AI setup (the ▾ of the AI switch).")
        if not self.credentials.get() and not _is_local(_base_url(ctx)):
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
        address = _base_url(ctx)
        if self._models_at != address and self._loading_at != address:
            self.refresh_models(context=ctx)
        cached = self._models if self._models_at == address else []
        return list(dict.fromkeys(_extra_models(ctx) + _offering(task, cached)))

    def refresh_models(self, *, context: RouteContext | None = None) -> None:
        """Refresh the cache off-thread; ignore superseded requests and old addresses."""
        source = context if context is not None else self.host
        address = _base_url(source)
        provider = OpenRouterProvider(base_url=address, api_key=self.credentials.get() or "")
        self._generation += 1
        generation = self._generation
        self._loading_at = address

        def finished(models: list[OpenRouterModel] | None, error: BaseException | None) -> None:
            if generation != self._generation:
                return
            self._loading_at = None
            if address != _base_url(source):
                return
            self._models_at = address
            self._models = list(models or [])
            if error is not None:
                self.host.log(f"Could not list the models: {error}")
            self.host.model_choices_changed(self.id)

        try:
            self.host.run_in_background(provider.models, finished)
        except Exception as exc:  # scheduling failed before the work started
            finished(None, exc)

    def provider(self, ctx: RouteContext, route: Route) -> OpenRouterProvider:
        """Capture the settings and key now; later ones apply to the next provider."""
        cached = self._models if self._models_at == _base_url(ctx) else []
        known = next((model for model in cached if model.id == route.model), None)
        # A text-only verdict needs the server's word about the model's modalities.
        sees_images = not (known and known.input_modalities and not known.sees_images)
        return OpenRouterProvider(route.model, _base_url(ctx), self.credentials.get() or "",
                                  sees_images=sees_images)

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
