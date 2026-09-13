"""Guard the design-token bridge between design/tokens and its generated artifacts.

The generator lives in ``scripts/build_tokens.mjs`` and needs Node plus the root
npm dependencies, which CI does not install. These tests therefore re-derive the
expected output in pure Python, so a token change that was not rebuilt fails the
normal test run instead of surfacing as a silent visual regression.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOKENS_DIR = REPO_ROOT / "design" / "tokens"
CSS_FILE = REPO_ROOT / "app" / "static" / "css" / "src" / "00-shell-tokens.css"
TAILWIND_FILE = TOKENS_DIR / "generated" / "tailwind.cjs"
TAILWIND_CONFIG = REPO_ROOT / "tailwind.config.js"

ALIAS_PATTERN = re.compile(r"^\{([^}]+)\}$")

DAISYUI_ROLES = {
    "primary": "color-action-default",
    "primary-content": "color-action-on",
    "secondary": "color-support-default",
    "secondary-content": "color-support-on",
    "accent": "color-highlight-default",
    "accent-content": "color-highlight-on",
    "neutral": "color-contrast-default",
    "neutral-content": "color-contrast-on",
    "base-100": "color-surface-page",
    "base-200": "color-surface-raised",
    "base-300": "color-surface-border",
    "base-content": "color-text-primary",
    "info": "color-status-info",
    "info-content": "color-status-info-on",
    "success": "color-status-ok",
    "success-content": "color-status-ok-on",
    "warning": "color-status-warn",
    "warning-content": "color-status-warn-on",
    "error": "color-status-critical",
    "error-content": "color-status-critical-on",
}


def _flatten(node, prefix=()):
    """Yield (dotted_path, raw_value) for every DTCG token below one node."""
    if isinstance(node, dict) and "$value" in node:
        yield ".".join(prefix), node["$value"]
        return
    if not isinstance(node, dict):
        return
    for key, child in node.items():
        if key.startswith("$"):
            continue
        yield from _flatten(child, (*prefix, key))


def _load(name):
    """Return the flattened tokens of one token file."""
    payload = json.loads((TOKENS_DIR / name).read_text(encoding="utf-8"))
    return dict(_flatten(payload))


def _resolved_semantic_tokens():
    """Return the semantic tokens with every alias resolved against the core layer."""
    core = _load("core.json")
    semantic = _load("semantic.json")
    everything = {**core, **semantic}

    resolved = {}
    for path, value in semantic.items():
        seen = set()
        while isinstance(value, str) and (match := ALIAS_PATTERN.match(value)):
            target = match.group(1)
            assert target not in seen, f"Alias-Zyklus bei {path}"
            seen.add(target)
            assert target in everything, f"{path} verweist auf unbekanntes Token {target}"
            value = everything[target]
        resolved[path.replace(".", "-")] = value
    return resolved


def _css_custom_properties():
    """Return the custom properties declared in the generated shell token file."""
    text = CSS_FILE.read_text(encoding="utf-8")
    return dict(re.findall(r"^\s*--([\w-]+):\s*(.+?);$", text, re.MULTILINE))


def _tailwind_module():
    """Return the generated Tailwind token module as a dictionary."""
    text = TAILWIND_FILE.read_text(encoding="utf-8")
    payload = text.split("module.exports =", 1)[1].rsplit(";", 1)[0]
    return json.loads(payload)


def test_every_semantic_token_reaches_the_generated_css():
    """Verify the CSS custom properties match the resolved semantic layer exactly."""
    expected = _resolved_semantic_tokens()
    actual = _css_custom_properties()

    assert actual == expected, (
        "00-shell-tokens.css passt nicht zu design/tokens/. "
        "Neu erzeugen mit: npm run build:tokens"
    )


def test_shell_layout_tokens_keep_the_names_the_application_reads():
    """Verify the names base.html and the shell CSS depend on are still emitted."""
    properties = _css_custom_properties()

    assert properties["sidebar-width"] == "264px"
    assert properties["sidebar-width-collapsed"] == "64px"
    assert properties["topbar-height"] == "56px"

    base_html = (REPO_ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    shell_layout = (REPO_ROOT / "app" / "static" / "css" / "src" / "99-shell-layout.css").read_text(
        encoding="utf-8"
    )

    assert "var(--sidebar-width)_minmax(0,1fr)" in base_html
    assert "--sidebar-width: var(--sidebar-width-collapsed);" in shell_layout


def test_daisyui_palette_is_derived_from_the_semantic_tokens():
    """Verify every DaisyUI role resolves to the semantic token it claims to use."""
    expected = _resolved_semantic_tokens()
    palette = _tailwind_module()["daisyui"]

    assert set(palette) == set(DAISYUI_ROLES)
    for role, token in DAISYUI_ROLES.items():
        assert palette[role] == expected[token], f"DaisyUI-Rolle {role} weicht von {token} ab"


def test_tailwind_theme_screens_match_the_four_breakpoints():
    """Verify Tailwind uses the four token breakpoints and no others."""
    screens = _tailwind_module()["screens"]

    assert screens == {"sm": "640px", "md": "768px", "lg": "1024px", "xl": "1440px"}


def test_tailwind_config_carries_no_literal_values():
    """Verify colors and breakpoints live in the token files, not in the config."""
    config = TAILWIND_CONFIG.read_text(encoding="utf-8")

    assert "design/tokens/generated/tailwind.cjs" in config
    assert not re.search(
        r"#[0-9a-fA-F]{3,8}\b", config
    ), "Farbliteral in tailwind.config.js. Werte gehoeren nach design/tokens/core.json."
    assert not re.search(
        r"^\s*(?!//)(?!\s*\*).*\b\d{3,4}px\b", config, re.MULTILINE
    ), "px-Literal in tailwind.config.js. Breakpoints kommen aus design/tokens/semantic.json."
