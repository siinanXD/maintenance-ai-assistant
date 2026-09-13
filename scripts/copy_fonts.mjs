/*
 * Die Werkbank-Schriften selbst hosten.
 *
 * Kopiert die benoetigten Schnitte aus den @fontsource-Paketen nach
 * app/static/fonts/ und erzeugt app/static/css/src/00-foundation/fonts.css mit den
 * @font-face-Regeln. Die Schriften stehen unter der SIL Open Font License; die
 * Lizenzdatei jeder Familie wird mitkopiert.
 *
 * Selbst gehostet statt von fonts.googleapis.com: kein Datentransfer an Dritte
 * beim Seitenaufruf, und die App bleibt in Hallen ohne Internetzugang lesbar.
 *
 * Nur bei geaenderter Auswahl noetig: npm run build:fonts
 */

import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT_DIR = dirname(dirname(fileURLToPath(import.meta.url)));
const FONTS_DIR = join(ROOT_DIR, "app", "static", "fonts");
const CSS_TARGET = join(ROOT_DIR, "app", "static", "css", "src", "00-foundation", "fonts.css");

/** Families, the CSS family name and the weights the design system uses. */
const FAMILIES = [
  { pkg: "ibm-plex-sans", family: "IBM Plex Sans", weights: [400, 500, 600] },
  { pkg: "ibm-plex-mono", family: "IBM Plex Mono", weights: [400, 500] },
  { pkg: "archivo", family: "Archivo", weights: [600, 700] },
  { pkg: "archivo-narrow", family: "Archivo Narrow", weights: [600, 700] }
];

/**
 * Copy the font files and write the @font-face rules.
 *
 * @returns {void}
 */
function main() {
  rmSync(FONTS_DIR, { recursive: true, force: true });
  const rules = [];
  const provenance = [];

  for (const { pkg, family, weights } of FAMILIES) {
    const source = join(ROOT_DIR, "node_modules", "@fontsource", pkg);
    const version = JSON.parse(readFileSync(join(source, "package.json"), "utf8")).version;
    const target = join(FONTS_DIR, pkg);
    mkdirSync(target, { recursive: true });
    copyFileSync(join(source, "LICENSE"), join(target, "LICENSE"));
    provenance.push(`@fontsource/${pkg}@${version}`);

    for (const weight of weights) {
      const file = `${pkg}-latin-${weight}-normal.woff2`;
      copyFileSync(join(source, "files", file), join(target, file));
      rules.push(
        [
          "@font-face {",
          `  font-family: "${family}";`,
          "  font-style: normal;",
          `  font-weight: ${weight};`,
          "  font-display: swap;",
          `  src: url("../fonts/${pkg}/${file}") format("woff2");`,
          "}"
        ].join("\n")
      );
    }
  }

  const css = [
    "/*",
    " * Erzeugt von scripts/copy_fonts.mjs. Nicht von Hand aendern.",
    ` * Quelle: ${provenance.join(", ")} (SIL Open Font License).`,
    " */",
    "",
    rules.join("\n\n"),
    ""
  ].join("\n");
  writeFileSync(CSS_TARGET, css, "utf8");
  console.log(`Schriften kopiert: ${rules.length} Schnitte aus ${provenance.join(", ")}`);
}

main();
