"""Guard the design-token bridge from the Figma export to CSS, Tailwind and legacy CSS.

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
TOKENS_FILE = TOKENS_DIR / "tokens.json"
APP_FILE = TOKENS_DIR / "app.json"
CSS_SRC = REPO_ROOT / "app" / "static" / "css" / "src"
TOKEN_CSS = CSS_SRC / "00-foundation" / "tokens.css"
TAILWIND_FILE = TOKENS_DIR / "generated" / "tailwind.cjs"
TAILWIND_CONFIG = REPO_ROOT / "tailwind.config.js"

FIGMA_SETS = ["core", "semantic", "semantic-dark", "layout", "typography", "effects"]
LIGHT_EMITTED = ["semantic", "layout", "typography", "effects", "app"]
DARK_SELECTOR = ':root[data-theme="maintenance-dark"]'
SANS_FALLBACK = ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"]
MONO_FALLBACK = ["ui-monospace", "SFMono-Regular", "Consolas", "monospace"]
ALIAS = re.compile(r"^\{([^}]+)\}$")


def _flatten(node, prefix=()):
    """Yield (path tuple, token dict) for every DTCG token below one node."""
    if isinstance(node, dict) and "$value" in node:
        yield prefix, node
        return
    if not isinstance(node, dict):
        return
    for key, child in node.items():
        if not key.startswith("$"):
            yield from _flatten(child, (*prefix, key))


def _sets():
    """Return every token set by name, including the app-owned set."""
    payload = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    sets = {name: dict(_flatten(payload[name])) for name in FIGMA_SETS}
    sets["app"] = dict(_flatten(json.loads(APP_FILE.read_text(encoding="utf-8"))))
    return sets


def _resolve(names):
    """Resolve aliases across the named sets and return path -> (type, value, set)."""
    sets = _sets()
    merged = {}
    origin = {}
    for name in names:
        for path, token in sets[name].items():
            merged[".".join(path)] = token
            origin[".".join(path)] = name

    def value_of(dotted, seen):
        raw = merged[dotted]["$value"]
        match = ALIAS.match(raw) if isinstance(raw, str) else None
        if not match:
            return raw
        target = match.group(1)
        assert target not in seen, f"Alias-Zyklus bei {dotted}"
        assert target in merged, f"{dotted} verweist auf unbekanntes Token {target}"
        return value_of(target, {*seen, target})

    return {
        dotted: (merged[dotted]["$type"], value_of(dotted, {dotted}), origin[dotted])
        for dotted in merged
    }


def _css_value(dotted, token_type, value):
    """Format a resolved token the way the generator writes it into CSS."""
    if token_type != "fontFamily":
        return str(value)
    fallback = MONO_FALLBACK if dotted.endswith(".mono") else SANS_FALLBACK
    return ", ".join(f'"{family}"' if " " in family else family for family in [value, *fallback])


def _css_block(selector):
    """Return the custom properties declared in one block of the generated token CSS."""
    text = TOKEN_CSS.read_text(encoding="utf-8")
    start = text.index(f"  {selector} {{")
    body = text[start : text.index("\n  }", start)]
    return dict(re.findall(r"^\s*--([\w-]+):\s*(.+?);$", body, re.MULTILINE))


def _tailwind_module():
    """Return the generated Tailwind token module as a dictionary."""
    text = TAILWIND_FILE.read_text(encoding="utf-8")
    return json.loads(text.split("module.exports =", 1)[1].rsplit(";", 1)[0])


def _luminance(hex_color):
    """Return the WCAG relative luminance of a #rrggbb color."""
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground, background):
    """Return the WCAG contrast ratio of two #rrggbb colors."""
    high, low = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_light_tokens_reach_the_generated_css_exactly():
    """Verify the :root block matches the resolved light sets, nothing more or less."""
    resolved = _resolve(["core", "semantic", "layout", "typography", "effects", "app"])
    expected = {
        dotted.replace(".", "-"): _css_value(dotted, token_type, value)
        for dotted, (token_type, value, set_name) in resolved.items()
        if set_name in LIGHT_EMITTED
    }

    assert (
        _css_block(":root") == expected
    ), "tokens.css passt nicht zu design/tokens/. Neu erzeugen mit: npm run build:tokens"


def test_dark_tokens_cover_exactly_the_light_semantic_roles():
    """Verify the dark block holds every semantic role and only those."""
    dark = _resolve(["core", "semantic-dark"])
    expected = {
        dotted.replace(".", "-"): str(value)
        for dotted, (_, value, set_name) in dark.items()
        if set_name == "semantic-dark"
    }
    light_roles = {"-".join(path) for path in _sets()["semantic"]}

    assert _css_block(DARK_SELECTOR) == expected
    assert set(expected) == light_roles


def test_shell_layout_tokens_keep_the_names_the_application_reads():
    """Verify the names base.html and the shell CSS depend on are still emitted."""
    properties = _css_block(":root")

    assert properties["sidebar-width"] == "264px"
    assert properties["sidebar-width-collapsed"] == "64px"
    assert properties["topbar-height"] == "64px"

    base_html = (REPO_ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    shell_layout = (CSS_SRC / "90-overrides" / "shell-layout.css").read_text(encoding="utf-8")

    assert "var(--sidebar-width)_minmax(0,1fr)" in base_html
    assert "--sidebar-width: var(--sidebar-width-collapsed);" in shell_layout


def test_tailwind_module_points_colors_at_custom_properties():
    """Verify Tailwind colors read the CSS variables and the other groups match the tokens."""
    module = _tailwind_module()
    properties = _css_block(":root")
    semantic_roles = {"-".join(path[1:]) for path in _sets()["semantic"]}

    assert set(module["colors"]) == semantic_roles
    for key, value in module["colors"].items():
        assert value == f"var(--color-{key})"
        assert f"color-{key}" in properties
    assert module["screens"] == {"sm": "640px", "md": "768px", "lg": "1024px", "xl": "1440px"}
    typography = {path[-1]: token["$value"] for path, token in _sets()["typography"].items()}
    assert {role: stack[0] for role, stack in module["fontFamily"].items()} == typography


def test_tokens_file_is_the_figma_export():
    """Verify tokens.json keeps the export layout and no hand-split set files return."""
    payload = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))

    assert [key for key in payload if not key.startswith("$")] == FIGMA_SETS
    assert payload["$metadata"]["source"].startswith("figma:")
    assert APP_FILE.exists()
    assert not list(TOKENS_DIR.glob("core.json")), "Handgepflegte Set-Dateien neben tokens.json"
    assert not list(TOKENS_DIR.glob("semantic.json")), "Handgepflegte Set-Dateien neben tokens.json"


def test_muted_text_meets_wcag_aa_on_every_ground():
    """Verify muted and secondary text keep 4.5:1 on canvas, surface and sunken grounds."""
    light = {dotted: value for dotted, (_, value, _s) in _resolve(["core", "semantic"]).items()}
    dark = {dotted: value for dotted, (_, value, _s) in _resolve(["core", "semantic-dark"]).items()}

    for palette in (light, dark):
        for text_role in ("color.text.muted", "color.text.secondary"):
            for ground in ("color.bg.canvas", "color.bg.surface", "color.bg.surface-sunken"):
                ratio = _contrast(palette[text_role], palette[ground])
                assert ratio >= 4.5, f"{text_role} auf {ground}: {ratio:.2f}:1"


def test_css_reads_design_tokens_not_legacy_variables():
    """Verify no stylesheet declares or reads the old --ui-*/--ops-* variables."""
    offenders = {
        str(path.relative_to(CSS_SRC)): sorted(set(re.findall(r"--(?:ui|ops)-[\w-]+", text)))
        for path in CSS_SRC.rglob("*.css")
        if re.search(r"--(?:ui|ops)-[\w-]+", text := path.read_text(encoding="utf-8"))
    }

    assert offenders == {}


def test_tailwind_config_carries_no_literal_values_and_no_daisyui():
    """Verify colors and breakpoints live in the tokens and DaisyUI stays removed."""
    config = TAILWIND_CONFIG.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", config, flags=re.S)
    package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))

    assert "design/tokens/generated/tailwind.cjs" in code
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", code), "Farbliteral in tailwind.config.js"
    assert not re.search(r"\b\d{3,4}px\b", code), "px-Literal in tailwind.config.js"
    assert "daisyui" not in code
    assert "daisyui" not in {
        **package.get("dependencies", {}),
        **package.get("devDependencies", {}),
    }
