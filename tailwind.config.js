/*
 * Farben und Breakpoints stammen aus design/tokens/. Werte gehoeren nicht in
 * diese Datei: geaendert wird core.json, danach `npm run build:tokens`.
 *
 * Bewusst nicht uebernommen sind radius und elevation. Beide wuerden Tailwinds
 * Standardskalen ueberschreiben und damit jedes vorhandene rounded-* und
 * shadow-* veraendern. Sie stehen als CSS-Custom-Properties bereit und werden
 * in Schritt 4 bis 6 des Werkbank-Briefs uebernommen, wenn die 295 Freihand-
 * Radien und 140 Freihand-Schatten abgeloest werden.
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
      screens: tokens.screens
    }
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: [{ maintenance: tokens.daisyui }]
  }
};
