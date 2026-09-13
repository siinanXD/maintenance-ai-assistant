/*
 * Farben, Breakpoints und Schriften stammen aus design/tokens/. Werte gehoeren
 * nicht in diese Datei: gestaltet wird in Figma, uebertragen per
 * scripts/figma/export_tokens.js, erzeugt mit `npm run build:tokens`.
 *
 * Die Farben verweisen auf CSS-Custom-Properties, damit Utilities dem dunklen
 * Modus folgen, sobald er eingeschaltet wird.
 *
 * Bewusst nicht uebernommen sind radius und elevation. Beide wuerden Tailwinds
 * Standardskalen ueberschreiben und damit jedes vorhandene rounded-* und
 * shadow-* veraendern; sie stehen als --radius-* und --elevation-* bereit.
 *
 * DaisyUI ist entfernt. Version 5 setzt Tailwind 4 voraus und hat mit Tailwind
 * 3.4 keine einzige Regel erzeugt; .btn, .badge und Co. stammen aus
 * app/static/css/src/ (siehe app/static/css/README.md).
 */

const tokens = require("./design/tokens/generated/tailwind.cjs");

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/**/*.js",
    "./frontend/src/**/*.{ts,tsx}"
  ],
  safelist: ["chat-history-item"],
  theme: {
    extend: {
      colors: tokens.colors,
      screens: tokens.screens,
      fontFamily: tokens.fontFamily
    }
  }
};
