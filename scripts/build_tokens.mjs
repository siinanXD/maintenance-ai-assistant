/*
 * Design-Token in die beiden Verbraucher der Anwendung uebersetzen:
 *
 *   app/static/css/src/00-shell-tokens.css   CSS-Custom-Properties, hell und dunkel
 *   design/tokens/generated/tailwind.cjs     Tailwind-Farben, Breakpoints, Schriften
 *
 * Quellen:
 *   design/tokens/tokens.json  Export der Figma-Datei (scripts/figma/export_tokens.js),
 *                              Sets core, semantic, semantic-dark, layout,
 *                              typography, effects. Nicht von Hand aendern.
 *   design/tokens/app.json     App-eigene Namen, die Figma nicht kennt
 *                              (--sidebar-width, Breakpoints). Von Hand gepflegt.
 *
 * Beide Ergebnisse sind eingecheckt, weil die CI nur die Frontend-Abhaengigkeiten
 * installiert und dieses Skript dort nicht laeuft. tests/test_design_tokens.py
 * prueft bei jedem Lauf, dass sie zur Quelle passen.
 *
 * Die Primitive aus "core" verlassen den Generator nicht. In der Anwendung soll
 * var(--color-action-primary) stehen, nie ein Rampenwert.
 */

import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import StyleDictionary from "style-dictionary";

/**
 * Return a path with forward slashes.
 *
 * Style Dictionary matches `source` as a glob, and globs treat a backslash as
 * an escape character. Auf Windows liefert path.join Backslashes, wodurch das
 * Muster still ins Leere laeuft: der Build meldet dann "No tokens" statt eines
 * Fehlers. Deshalb laufen alle Pfade hier durch diese Funktion.
 *
 * @param {string} value One filesystem path.
 * @returns {string} The same path with forward slashes.
 */
function posix(value) {
  return value.split("\\").join("/");
}

const ROOT_DIR = posix(dirname(dirname(fileURLToPath(import.meta.url))));
const TOKENS_DIR = posix(join(ROOT_DIR, "design", "tokens"));
const TOKENS_FILE = `${TOKENS_DIR}/tokens.json`;
const APP_FILE = `${TOKENS_DIR}/app.json`;
const SETS_DIR = posix(join(ROOT_DIR, "tmp", "token-sets"));
const GENERATED_DIR = posix(join(TOKENS_DIR, "generated"));
const CSS_TARGET = posix(join(ROOT_DIR, "app", "static", "css", "src", "00-shell-tokens.css"));
const TAILWIND_TARGET = posix(join(GENERATED_DIR, "tailwind.cjs"));

const FIGMA_SETS = ["core", "semantic", "semantic-dark", "layout", "typography", "effects"];
const LIGHT_SOURCES = ["core", "semantic", "layout", "typography", "effects", "app"];
const LIGHT_EMITTED = new Set(["semantic", "layout", "typography", "effects", "app"]);
const DARK_SOURCES = ["core", "semantic-dark"];
const DARK_SELECTOR = ':root[data-theme="maintenance-dark"]';

const SANS_FALLBACK = ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"];
const MONO_FALLBACK = ["ui-monospace", "SFMono-Regular", "Consolas", "monospace"];

const BANNER = [
  "Erzeugt von scripts/build_tokens.mjs. Nicht von Hand aendern.",
  "Quelle: design/tokens/tokens.json (Figma-Export) und design/tokens/app.json.",
  "Neu erzeugen mit: npm run build:tokens"
];

/**
 * Split the token sources into one file per set and return their paths by set name.
 *
 * Style Dictionary merges its source files into one tree, so aliases resolve
 * across sets. semantic and semantic-dark share every path and therefore never
 * go into the same run; each run gets exactly the sets it needs.
 *
 * @returns {Record<string, string>} Unpacked file path per set name.
 */
function unpackSets() {
  const payload = JSON.parse(readFileSync(TOKENS_FILE, "utf8"));
  const missing = FIGMA_SETS.filter((name) => !(name in payload));
  if (missing.length > 0) {
    throw new Error(`tokens.json fehlen die Sets: ${missing.join(", ")}`);
  }
  if (!existsSync(APP_FILE)) {
    throw new Error(`App-Token fehlen: ${APP_FILE}`);
  }

  rmSync(SETS_DIR, { recursive: true, force: true });
  mkdirSync(SETS_DIR, { recursive: true });
  const paths = {};
  for (const name of FIGMA_SETS) {
    paths[name] = `${SETS_DIR}/${name}.json`;
    writeFileSync(paths[name], JSON.stringify(payload[name], null, 2), "utf8");
  }
  paths.app = `${SETS_DIR}/app.json`;
  writeFileSync(paths.app, readFileSync(APP_FILE, "utf8"), "utf8");
  return paths;
}

/**
 * Resolve every alias across the given sets and return the flat token list.
 *
 * @param {string[]} sets Set names to load together.
 * @param {Record<string, string>} paths Unpacked file path per set name.
 * @returns {Promise<Array<{path: string[], $type: string, $value: unknown, set: string}>>}
 */
async function resolveTokens(sets, paths) {
  const dictionary = new StyleDictionary({
    source: sets.map((name) => paths[name]),
    usesDtcg: true,
    log: { verbosity: "verbose" },
    platforms: { resolved: {} }
  });
  const { allTokens } = await dictionary.getPlatformTokens("resolved");
  return allTokens.map((token) => ({
    path: token.path,
    $type: token.$type,
    $value: token.$value,
    set: posix(token.filePath).split("/").pop().replace(/\.json$/, "")
  }));
}

/**
 * Return the CSS value for a token, adding fallback stacks to font families.
 *
 * @param {{path: string[], $type: string, $value: unknown}} token One resolved token.
 * @returns {string} The CSS value.
 */
function cssValue(token) {
  if (token.$type === "fontFamily") {
    return fontStack(token).map((family) => (family.includes(" ") ? `"${family}"` : family)).join(", ");
  }
  return String(token.$value);
}

/**
 * Return the font family followed by its fallback stack.
 *
 * @param {{path: string[], $value: unknown}} token One typography token.
 * @returns {string[]} Families in priority order.
 */
function fontStack(token) {
  const fallback = token.path[token.path.length - 1] === "mono" ? MONO_FALLBACK : SANS_FALLBACK;
  return [String(token.$value), ...fallback];
}

/**
 * Render one CSS rule block of custom properties.
 *
 * @param {string} selector The rule selector.
 * @param {Array<{path: string[], $type: string, $value: unknown}>} tokens Tokens to declare.
 * @returns {string[]} Lines of the block, indented for the base layer.
 */
function cssBlock(selector, tokens) {
  return [
    `  ${selector} {`,
    ...tokens.map((token) => `    --${token.path.join("-")}: ${cssValue(token)};`),
    "  }"
  ];
}

/**
 * Build both token artifacts.
 *
 * @returns {Promise<void>} Resolves once every file is written.
 */
async function main() {
  const paths = unpackSets();
  const light = (await resolveTokens(LIGHT_SOURCES, paths)).filter((token) => LIGHT_EMITTED.has(token.set));
  const dark = (await resolveTokens(DARK_SOURCES, paths)).filter((token) => token.set === "semantic-dark");

  const lightColors = light.filter((token) => token.set === "semantic").map((token) => token.path.join("."));
  const darkColors = dark.map((token) => token.path.join("."));
  const unmatched = lightColors.filter((path) => !darkColors.includes(path));
  if (unmatched.length > 0 || lightColors.length !== darkColors.length) {
    throw new Error(`Hell und dunkel decken nicht dieselben Rollen ab: ${unmatched.join(", ")}`);
  }

  const css = [
    "/*",
    ...BANNER.map((line) => ` * ${line}`),
    " *",
    ` * Dunkel ist vorbereitet, aber noch nirgends eingeschaltet: ${DARK_SELECTOR}.`,
    " */",
    "",
    "@layer base {",
    ...cssBlock(":root", light),
    "",
    ...cssBlock(DARK_SELECTOR, dark),
    "}",
    ""
  ].join("\n");

  const colors = Object.fromEntries(
    light
      .filter((token) => token.set === "semantic")
      .map((token) => [token.path.slice(1).join("-"), `var(--${token.path.join("-")})`])
  );
  const screens = Object.fromEntries(
    light
      .filter((token) => token.set === "app" && token.path[0] === "breakpoint")
      .map((token) => [token.path[1], String(token.$value)])
  );
  const fontFamily = Object.fromEntries(
    light.filter((token) => token.set === "typography").map((token) => [token.path[token.path.length - 1], fontStack(token)])
  );
  const tailwind = [
    "/*",
    ...BANNER.map((line) => ` * ${line}`),
    " */",
    "",
    `module.exports = ${JSON.stringify({ colors, screens, fontFamily }, null, 2)};`,
    ""
  ].join("\n");

  mkdirSync(GENERATED_DIR, { recursive: true });
  writeFileSync(CSS_TARGET, css, "utf8");
  writeFileSync(TAILWIND_TARGET, tailwind, "utf8");
  writeFileSync(`${GENERATED_DIR}/.gitattributes`, "tailwind.cjs linguist-generated=true\n", "utf8");

  console.log(
    `Design-Token erzeugt: ${light.length} hell, ${dark.length} dunkel -> ` +
      [CSS_TARGET, TAILWIND_TARGET].map((path) => path.replace(`${ROOT_DIR}/`, "")).join(", ")
  );
}

await main();
