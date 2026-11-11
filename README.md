# OpenRouter for SlideMage

Use [OpenRouter](https://openrouter.ai/)'s models as SlideMage's AI: one API key gives you models from Anthropic,
OpenAI, Google, DeepSeek, Mistral and many more, for chat, image descriptions, translation and fixes.

1. Get a key at [openrouter.ai/keys](https://openrouter.ai/keys).
2. Paste it under **Settings → AI → OpenRouter** and save it.
3. Choose a model in **AI setup** (the ▾ of the AI switch), for example `deepseek/deepseek-chat`.

The plugin works with any OpenAI-compatible server too: set its **Base URL** (for example
`https://api.openai.com/v1`, or `http://localhost:1234/v1` for LM Studio) and its key. A model the server does
not list can be added under **Extra model IDs**.

Your slides and prompts go to the server you set, and the model provider OpenRouter routes them to.

## Development

SlideMage loads the package folder named after `plugin.toml`'s `id`, replacing `-` with `_`. Use relative
imports inside that package: `from . import helpers`, or `from ..helpers import something` in a subpackage.
They must stay inside the package; `from .. import helpers` at the package root is invalid. The loader imports
the package directly from its folder without adding the plugin checkout to `sys.path`.

In a frozen (PyInstaller-built) SlideMage, a plugin may import only:

- `slidemage.plugin_api` from SlideMage, with API 1's `Host`, `Deck` and other public API types and services.
- The Python standard library available on the build platform, excluding `tkinter`, `turtle`, `turtledemo`,
  `idlelib`, `test`, `ensurepip`, `lib2to3`, `pydoc_data`, `this` and `antigravity` (the `EXCLUDED` names in
  SlideMage's `plugins/selftest.py`). Private top-level modules (names starting with `_`) are also excluded,
  except `_thread`. The list comes from `sys.stdlib_module_names`; `bundled_stdlib_modules()` filters out
  those exclusions and modules unavailable on that platform (for example, `msvcrt` on Linux).
- These PySide6 modules: `QtCore`, `QtGui`, `QtWidgets`, `QtNetwork` and `QtSvg`.
- Its own package, using relative imports as above.

PyInstaller normally bundles only modules SlideMage itself imports. SlideMage explicitly bundles the
standard-library list above (including package submodules) and those five PySide6 modules for plugins;
other modules installed in your development environment are not guaranteed in the frozen app.
`slidemage --self-test --plugins` checks that the permitted standard-library modules are importable and
loads a minimal plugin through the real loader. The release build runs it on every platform; it does not
load your plugin. To run your checkout, set `SLIDEMAGE_PLUGIN_PATH` to the folder containing `plugin.toml`
and start SlideMage.

`activate(host)` registers contributions through `host.add_command(...)` and `host.add_menu_entry("deck", ...)`
in the example. All `add_*` calls belong in `activate()`, which must be quick and do no network work. Its
`enabled` callback disables the command when no deck is open, and `run(deck)` calls `host.show_message(...)`.
The `Host` and `Deck` imports are under `TYPE_CHECKING` only, with postponed annotations, so the example
package can be imported without SlideMage installed.

`python build.py --check` checks the plugin against the catalogue's conventions: `plugin.toml`, the package
and its `activate(host)`, the imports (including relative imports that climb above the package root), no
compiled files, and the changelog rules below. Its absolute-import allowlist remains
`slidemage.plugin_api`, the standard library, PySide6 and the plugin's own package; it does not verify the
narrower frozen-app availability listed above. The **Check** workflow runs it and the tests on every push.

Run `python -m pytest -q` for the changelog and import-lint tests and the example's FakeHost tests. The latter skip cleanly
when `slidemage.plugin_api` is not importable. To include them against a SlideMage source checkout, use
`PYTHONPATH=/path/to/SlideMage/src python -m pytest -q` with a Python environment that has pytest installed.

`python build.py` checks and then builds `dist/<id>-<version>.smplugin` (a zip of `plugin.toml`, `LICENSE`,
`CHANGELOG.md` and the package) and its `.sha256`. The build is reproducible: the same files always give the same hash.

### Changelog and releases

Keep `CHANGELOG.md` in the app's format. For each change, bump `version` in `plugin.toml` and append
an entry in the same commit, oldest first. Separate paragraphs with blank lines:

```text
v1.2.0 (2026-11-02, feature): Technical details of the change.

NEW: An optional short summary of the release.
- Describe a change users will notice in plain words.
- Describe another change or fix.
```

Every entry needs one `NEW:` paragraph with at least one nonempty `- ` bullet. For a major version
increase from the preceding entry, add a separate `BREAKING:` paragraph explaining what changed and
what users need to do. The first entry has no earlier version to compare. The checker requires entries
to increase strictly and `plugin.toml` to match the newest entry; it checks all entries, with no
exemption for older ones. `python build.py --check` runs the check locally and the Check workflow runs
it on pushes and pull requests. The changelog is included in the plugin archive.

To release, commit the version and changelog, then tag and push, for example
`git tag v1.2.0 && git push origin v1.2.0`. The Release workflow verifies the tag and builds and
publishes the asset. It uses `python release_notes.py v1.2.0` to turn the `NEW:` and `BREAKING:`
paragraphs into the GitHub release notes. As in SlideMage, it finds the previous tag from Git and
includes entries after that tag through the new version; if no previous tag is found, it includes only
the tagged entry. For a local preview, pass `--previous v1.0.0` to select the previous release
explicitly, and optionally `--repo OWNER/REPOSITORY` to add a GitHub comparison link.

A published version never changes: never replace or delete its asset; a fix is a new version. Drafts and
pre-releases are not listed in the catalogue.
