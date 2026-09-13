"""Helpers for rendering optional frontend build assets."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from flask import current_app, url_for
from markupsafe import Markup, escape


def register_frontend_asset_helpers(app):
    """Register Jinja helpers for optional frontend build assets."""

    @app.template_global()
    def react_entrypoint(entry_name):
        """Render the script tags for a Vite React entrypoint if it exists."""
        return render_react_entrypoint(entry_name)

    @app.template_global()
    def static_asset_url(filename):
        """Return a static URL with a content hash, so browsers reload changed files."""
        path = Path(current_app.static_folder) / filename
        return f"{url_for('static', filename=filename)}?v={_file_version(str(path), _mtime(path))}"

    @app.template_global()
    def static_scripts_version():
        """Return one version for the page island scripts that app.js imports lazily."""
        folder = Path(current_app.static_folder)
        files = sorted([*folder.glob("pages/*.js"), *folder.glob("core/*.js"), folder / "app.js"])
        return _files_version(tuple((str(path), _mtime(path)) for path in files))


def _mtime(path):
    """Return a file's modification time, or 0 when it is missing."""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


@lru_cache(maxsize=64)
def _file_version(path, mtime):
    """Return a short content hash; the mtime argument invalidates the cache."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:10]
    except OSError:
        return "missing"


@lru_cache(maxsize=4)
def _files_version(entries):
    """Return a short combined hash for several files."""
    digest = hashlib.sha256()
    for path, mtime in entries:
        digest.update(_file_version(path, mtime).encode())
    return digest.hexdigest()[:10]


def render_react_entrypoint(entry_name):
    """Return module script markup for a React entrypoint from the Vite manifest."""
    if not isinstance(entry_name, str) or not entry_name.strip():
        current_app.logger.warning("React entrypoint name is invalid: %r", entry_name)
        return Markup("")

    manifest = load_react_manifest()
    entry = react_manifest_entry(manifest, entry_name)
    if not isinstance(entry, dict):
        current_app.logger.info("React entrypoint missing from manifest: %s", entry_name)
        return Markup("")

    asset_file = entry.get("file")
    if not isinstance(asset_file, str) or not asset_file:
        current_app.logger.warning("React entrypoint has no file: %s", entry_name)
        return Markup("")

    tags = []
    for imported_file in imported_react_files(manifest, entry):
        tags.append(
            '<link rel="modulepreload" href="{}">'.format(
                escape(url_for("static", filename=f"react/{imported_file}")),
            ),
        )
    for css_file in entry.get("css", []):
        if isinstance(css_file, str) and css_file:
            tags.append(
                '<link rel="stylesheet" href="{}">'.format(
                    escape(url_for("static", filename=f"react/{css_file}")),
                ),
            )
    tags.append(
        '<script type="module" src="{}"></script>'.format(
            escape(url_for("static", filename=f"react/{asset_file}")),
        ),
    )
    return Markup("\n".join(tags))


def imported_react_files(manifest, entry):
    """Return imported Vite chunk files for a manifest entry."""
    imported_files = []
    seen_imports = set()

    def collect_imports(current_entry):
        """Collect imported files recursively while preserving manifest order."""
        imports = current_entry.get("imports", [])
        if not isinstance(imports, list):
            current_app.logger.warning(
                "React manifest imports have invalid type: %s",
                type(imports),
            )
            return

        for import_name in imports:
            if not isinstance(import_name, str):
                current_app.logger.warning("React manifest import key is invalid: %r", import_name)
                continue
            if import_name in seen_imports:
                continue
            seen_imports.add(import_name)
            imported_entry = manifest.get(import_name)
            if not isinstance(imported_entry, dict):
                current_app.logger.warning("React manifest import is missing: %s", import_name)
                continue
            imported_file = imported_entry.get("file")
            if isinstance(imported_file, str) and imported_file:
                imported_files.append(imported_file)
            else:
                current_app.logger.warning("React manifest import has no file: %s", import_name)
            collect_imports(imported_entry)

    collect_imports(entry)
    return imported_files


def react_manifest_entry(manifest, entry_name):
    """Return a manifest entry by exact key or normalized path suffix."""
    entry = manifest.get(entry_name)
    if isinstance(entry, dict):
        return entry

    normalized_entry_name = entry_name.replace("\\", "/")
    matches = [
        candidate
        for manifest_key, candidate in manifest.items()
        if isinstance(manifest_key, str)
        and manifest_key.replace("\\", "/").endswith(normalized_entry_name)
        and isinstance(candidate, dict)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        current_app.logger.warning(
            "React entrypoint is ambiguous in manifest: %s",
            entry_name,
        )
    return None


def load_react_manifest():
    """Load the Vite manifest for optional React islands."""
    manifest_path = Path(current_app.static_folder or "") / "react" / ".vite" / "manifest.json"

    if not manifest_path.exists():
        return {}

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        current_app.logger.warning("React manifest could not be read: %s", error)
        return {}
    except json.JSONDecodeError as error:
        current_app.logger.warning("React manifest contains invalid JSON: %s", error)
        return {}

    if not isinstance(manifest_data, dict):
        current_app.logger.warning("React manifest has invalid root type: %s", type(manifest_data))
        return {}

    return manifest_data
