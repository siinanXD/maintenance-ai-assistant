/*
 * Design-Token aus design/tokens/*.json in die beiden Verbraucher uebersetzen:
 *
 *   app/static/css/src/00-shell-tokens.css   CSS-Custom-Properties
 *   design/tokens/generated/tailwind.cjs     Tailwind-Theme und DaisyUI-Palette
 *
 * Beide Ergebnisse sind eingecheckt, weil die CI nur die Frontend-Abhaengigkeiten
 * installiert und dieses Skript dort nicht laeuft. tests/test_design_tokens.py
 * prueft bei jedem Lauf, dass sie zur Quelle passen.
 *
 * Nur die semantische Ebene verlaesst den Generator. Die Primitive aus core.json
 * sind Eingabe und sollen in der Anwendung nicht auftauchen.
 */

import { existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
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
const GENERATED_DIR = posix(join(TOKENS_DIR, "generated"));
const CSS_TARGET = posix(join(ROOT_DIR, "app", "static", "css", "src", "00-shell-tokens.css"));
const TAILWIND_TARGET = posix(join(GENERATED_DIR, "tailwind.cjs"));

const BANNER = [
  "Erzeugt von scripts/build_tokens.mjs. Nicht von Hand aendern.",
  "Quelle: design/tokens/core.json und design/tokens/semantic.json.",
  "Neu erzeugen mit: npm run build:tokens"
];

/**
 * Return the token source files, ignoring Tokens Studio's bookkeeping files.
 *
 * Beim Multi-File-Sync legt Tokens Studio $metadata.json (Reihenfolge der Sets)
 * und $themes.json (Theme-Liste) im selben Ordner ab. Style Dictionary laesst
 * beide nachweislich links liegen, die Ausgabe bleibt mit ihnen byteidentisch.
 * Die Liste ist hier trotzdem explizit, damit nicht eine kuenftige Version oder
 * ein anderes Format still Muell aus $themes.json einliest -- das ist ein Array
 * und kein Token-Set. Zusaetzlich schlaegt ein leerer Ordner so laut fehl.
 *
 * @returns {string[]} Absolute paths of the token files, in a stable order.
 */
function tokenSourceFiles() {
  const files = readdirSync(TOKENS_DIR)
    .filter((name) => name.endsWith(".json") && !name.startsWith("$"))
    .sort();
  if (files.length === 0) {
    throw new Error(`Keine Token-Dateien in ${TOKENS_DIR}`);
  }
  return files.map((name) => `${TOKENS_DIR}/${name}`);
}

/**
 * Return whether a token came from the semantic layer.
 *
 * @param {{filePath: string}} token One resolved design token.
 * @returns {boolean} True when the token is part of the semantic layer.
 */
function isSemantic(token) {
  return token.filePath.endsWith("semantic.json");
}

/**
 * Return the CSS custom property name for a token.
 *
 * @param {{path: string[]}} token One resolved design token.
 * @returns {string} The custom property name without the leading dashes.
 */
function cssName(token) {
  return token.path.join("-");
}

/**
 * Return the token value as a plain string.
 *
 * @param {{$value?: unknown, value?: unknown}} token One resolved design token.
 * @returns {string} The resolved value.
 */
function tokenValue(token) {
  return String(token.$value ?? token.value);
}

/**
 * Return the tokens of one top-level group keyed by their remaining path.
 *
 * @param {Array<object>} tokens All semantic tokens.
 * @param {string} group The top-level group name.
 * @returns {Record<string, string>} Values keyed by the dash-joined rest path.
 */
function group(tokens, group_) {
  const result = {};
  for (const token of tokens) {
    if (token.path[0] !== group_ || token.path.length < 2) continue;
    result[token.path.slice(1).join("-")] = tokenValue(token);
  }
  return result;
}

StyleDictionary.registerFormat({
  name: "maintenance/css-variables",
  /**
   * Render the semantic tokens as custom properties inside Tailwind's base layer.
   *
   * @param {{dictionary: {allTokens: Array<object>}}} context Style Dictionary context.
   * @returns {string} The CSS file contents.
   */
  format({ dictionary }) {
    const lines = dictionary.allTokens
      .filter(isSemantic)
      .map((token) => `    --${cssName(token)}: ${tokenValue(token)};`);
    return [
      "/*",
      ...BANNER.map((line) => ` * ${line}`),
      " */",
      "",
      "@layer base {",
      "  :root {",
      ...lines,
      "  }",
      "}",
      ""
    ].join("\n");
  }
});

StyleDictionary.registerFormat({
  name: "maintenance/tailwind-module",
  /**
   * Render the Tailwind theme fragment and the DaisyUI palette.
   *
   * @param {{dictionary: {allTokens: Array<object>}}} context Style Dictionary context.
   * @returns {string} The CommonJS module contents.
   */
  format({ dictionary }) {
    const tokens = dictionary.allTokens.filter(isSemantic);
    const colors = group(tokens, "color");
    const payload = {
      colors,
      screens: group(tokens, "breakpoint"),
      radius: group(tokens, "radius"),
      elevation: group(tokens, "elevation"),
      daisyui: {
        primary: colors["action-default"],
        "primary-content": colors["action-on"],
        secondary: colors["support-default"],
        "secondary-content": colors["support-on"],
        accent: colors["highlight-default"],
        "accent-content": colors["highlight-on"],
        neutral: colors["contrast-default"],
        "neutral-content": colors["contrast-on"],
        "base-100": colors["surface-page"],
        "base-200": colors["surface-raised"],
        "base-300": colors["surface-border"],
        "base-content": colors["text-primary"],
        info: colors["status-info"],
        "info-content": colors["status-info-on"],
        success: colors["status-ok"],
        "success-content": colors["status-ok-on"],
        warning: colors["status-warn"],
        "warning-content": colors["status-warn-on"],
        error: colors["status-critical"],
        "error-content": colors["status-critical-on"]
      }
    };
    return [
      "/*",
      ...BANNER.map((line) => ` * ${line}`),
      " */",
      "",
      `module.exports = ${JSON.stringify(payload, null, 2)};`,
      ""
    ].join("\n");
  }
});

/**
 * Build both token artifacts.
 *
 * @returns {Promise<void>} Resolves once every file is written.
 */
async function main() {
  mkdirSync(GENERATED_DIR, { recursive: true });

  const dictionary = new StyleDictionary({
    source: tokenSourceFiles(),
    usesDtcg: true,
    log: { verbosity: "verbose" },
    platforms: {
      css: {
        transformGroup: "css",
        files: [
          {
            destination: CSS_TARGET,
            format: "maintenance/css-variables",
            options: { usesDtcg: true }
          }
        ]
      },
      tailwind: {
        transformGroup: "js",
        files: [
          {
            destination: TAILWIND_TARGET,
            format: "maintenance/tailwind-module",
            options: { usesDtcg: true }
          }
        ]
      }
    }
  });

  await dictionary.buildAllPlatforms();

  const missing = [CSS_TARGET, TAILWIND_TARGET].filter((path) => !existsSync(path));
  if (missing.length > 0) {
    throw new Error(`Token-Build hat nichts geschrieben: ${missing.join(", ")}`);
  }

  writeFileSync(`${GENERATED_DIR}/.gitattributes`, "tailwind.cjs linguist-generated=true\n", "utf8");
  const written = [CSS_TARGET, TAILWIND_TARGET].map((path) => path.replace(`${ROOT_DIR}/`, ""));
  console.log(`Design-Token erzeugt: ${written.join(", ")}`);
}

await main();
