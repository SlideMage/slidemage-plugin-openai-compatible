# SPDX-FileCopyrightText: 2026 Stefan Palan, Jürgen Fleiß
# SPDX-License-Identifier: GPL-3.0-or-later
"""Import boundaries enforced by build.py --check."""
import pytest

import build


@pytest.fixture
def plugin_root(tmp_path, monkeypatch):
    (tmp_path / "plugin.toml").write_text('''\
id = "example"
name = "Example"
version = "0.1.0"
api_version = 1
requires_slidemage = ">=9.0"
summary = "A test plugin."
author = "Test Author"
homepage = "https://example.invalid/plugin"
license = "GPL-3.0-or-later"
needs = []
network = []
''', encoding="utf-8")
    for name, text in {
        "LICENSE": "Test license\n",
        "README.md": "Test plugin\n",
        "CHANGELOG.md": "v0.1.0 (2026-10-28, initial): Test plugin.\n\nNEW:\n- Test plugin.\n",
    }.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "example").mkdir()
    (tmp_path / "example" / "__init__.py").write_text("def activate(host):\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(build, "ROOT", tmp_path)
    return tmp_path


def write_source(root, filename, source):
    path = root / "example" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("filename, source", [
    ("__init__.py", "from . import helpers"),
    ("module.py", "from .helpers import value"),
    ("sub/__init__.py", "from .. import helpers"),
    ("sub/module.py", "from ..helpers import value"),
    ("sub/module.py", "from . import sibling"),
    ("sub/nested/__init__.py", "from ... import helpers"),
    ("sub/nested/module.py", "from ...helpers import value"),
])
def test_relative_imports_inside_package_are_allowed(plugin_root, filename, source):
    path = write_source(plugin_root, filename, source)
    assert build.check_imports(path, "example") == []


@pytest.mark.parametrize("filename, source, imported", [
    ("__init__.py", "from .. import outside", ".."),
    ("module.py", "from ..outside import value", "..outside"),
    ("sub/__init__.py", "from ... import outside", "..."),
    ("sub/module.py", "from ...outside import value", "...outside"),
    ("sub/nested/__init__.py", "from .... import outside", "...."),
    ("sub/nested/module.py", "from ....outside import value", "....outside"),
])
def test_relative_imports_above_package_are_rejected(plugin_root, filename, source, imported):
    path = write_source(plugin_root, filename, source)
    assert build.check_imports(path, "example") == [
        f"example/{filename}:1: relative import {imported} climbs above package root example"
    ]


@pytest.mark.parametrize("source", [
    "import slidemage.plugin_api",
    "from slidemage import plugin_api",
    "from slidemage.plugin_api import Host, Deck",
    "import pathlib",
    "from urllib.request import urlopen",
    "import tkinter",  # the lint allows stdlib; frozen-app availability is documented separately
    "import PySide6.QtWidgets",
    "from PySide6 import QtSvg",
    "import example.helpers",
    "from example import helpers",
    "from example.helpers import value",
])
def test_absolute_import_allowlist_is_preserved(plugin_root, source):
    path = write_source(plugin_root, "module.py", source)
    assert build.check_imports(path, "example") == []


@pytest.mark.parametrize("source, imported", [
    ("import requests", "requests"),
    ("from requests import get", "requests"),
    ("import slidemage", "slidemage"),
    ("from slidemage import project", "slidemage.project"),
    ("from slidemage.plugins import loader", "slidemage.plugins"),
    ("import slidemage.plugin_api_private", "slidemage.plugin_api_private"),
    ("import example_other", "example_other"),
])
def test_other_absolute_imports_are_rejected(plugin_root, source, imported):
    path = write_source(plugin_root, "module.py", source)
    assert build.check_imports(path, "example") == [f"example/module.py:1: imports {imported}"]


def test_check_reports_escaping_imports_in_nested_code(plugin_root, capsys):
    write_source(plugin_root, "sub/module.py", "if False:\n    from ...outside import value")
    assert build.main(["--check"]) == 1
    assert capsys.readouterr().err == (
        "error: example/sub/module.py:2: relative import ...outside climbs above package root example\n"
    )
    assert not (plugin_root / "dist").exists()


def test_check_accepts_valid_plugin_without_building(plugin_root, capsys):
    assert build.main(["--check"]) == 0
    assert capsys.readouterr().err == ""
    assert not (plugin_root / "dist").exists()
