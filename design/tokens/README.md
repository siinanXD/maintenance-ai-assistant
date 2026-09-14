# Design-Token

Gestaltet wird in Figma, gebaut wird aus diesem Ordner. Werte ändert man nie in
`tailwind.config.js` und nie direkt in den Seitenstilen.

## Der Weg eines Werts

```
Figma-Datei "Maintenance AI — Design System & Redesign"
  │  scripts/figma/export_tokens.js  (läuft über die Figma-MCP-Anbindung von Claude Code)
  ▼
design/tokens/tokens.json            Export, nicht von Hand ändern
design/tokens/app.json               App-eigene Namen, von Hand gepflegt
  │  npm run build:tokens
  ▼
app/static/css/src/00-foundation/tokens.css   CSS-Custom-Properties, hell und dunkel
design/tokens/generated/tailwind.cjs     Tailwind-Farben, Breakpoints, Schriften
  │  var(--color-…), var(--space-…), var(--radius-…)
  ▼
app/static/css/src/10-legacy, 15-pages, 20-components
```

Übertragen heißt: Claude Code führt `scripts/figma/export_tokens.js` gegen die
Datei aus und speichert das Ergebnis als `tokens.json`. Ein Figma-Plugin, ein
GitHub-Token oder ein Sync-Branch sind dafür nicht nötig.

## tokens.json

| Set | Quelle in Figma | Inhalt |
| --- | --- | --- |
| `core` | Sammlung „1 Primitives" | Farbrampen (`color.neutral.500`, `color.signal.500`) |
| `semantic` | „2 Semantic", Modus Light | Rollen (`color.action.primary`, `color.text.muted`) |
| `semantic-dark` | „2 Semantic", Modus Dark | dieselben Rollen, dunkle Werte |
| `layout` | „3 Layout" | `space.*`, `radius.*`, `size.*` in px |
| `typography` | Textstile | Familie je Rolle: `font.display`, `label`, `body`, `mono` |
| `effects` | Effektstile `elevation/*` | Schatten und Fokusring |

Nur die Rollen erreichen die Anwendung. Die Rampen aus `core` sind Eingabe:
in CSS steht `var(--color-action-primary)`, nie ein Rampenwert.

## app.json

Namen, die die Anwendung liest, Figma aber nicht kennt. `--sidebar-width`,
`--sidebar-width-collapsed` und `--topbar-height` verweisen per Alias auf
`size.*` aus Figma; die vier Breakpoints (640/768/1024/1440) sind reine
App-Regeln.

## Dunkel

Der dunkle Satz steht unter `:root[data-theme="maintenance-dark"]`. `base.html`
setzt das Attribut vor dem ersten Paint: gespeicherte Wahl aus dem Benutzermenü
(`localStorage.maintenance_theme`), sonst die Systemeinstellung. Die Seitenstile
tragen keine festen Farben mehr, nur Schatten, Abdunklungen hinter Dialogen und
halbtransparente Weißkanten auf der Sidebar (in beiden Designs dunkel) bleiben
Literale. `tests/test_design_tokens.py` hält das fest.

## Ältere Seitenstile

Alle Stylesheets lesen die Token direkt. Die früheren `--ui-*`- und
`--ops-*`-Variablen wurden durch die Token ersetzt, auf die sie zeigten.
`app/static/css/src/90-overrides/token-overrides.css` setzt die Token dort
durch, wo ältere Regeln andere Token wählen als das Werkbank-Design:
Shell-Flächen, aktive Navigation, Zähler, Kartenleisten, Verweise, Status-Badges.

Neue Regeln gehören nicht dorthin. Neues CSS liest die Token direkt.

## Schriften

Selbst gehostet unter `app/static/fonts/`, erzeugt von `npm run build:fonts`
aus den `@fontsource`-Paketen (SIL Open Font License, Lizenzdateien liegen
bei). Kein Aufruf von fonts.googleapis.com, die App bleibt ohne Internet lesbar.

## Was der Drift-Wächter prüft

`tests/test_design_tokens.py` leitet die erwartete Ausgabe in reinem Python neu
her, weil die CI den Node-Generator nicht ausführt. Er schlägt an, wenn

- `00-foundation/tokens.css` hell oder dunkel nicht exakt zu `tokens.json` passt,
- Tailwind-Farben, Breakpoints oder Schriften von den Token abweichen,
- gedämpfter oder sekundärer Text auf Seiten-, Karten- oder abgesenktem
  Hintergrund unter **4,5:1** Kontrast fällt (hell und dunkel),
- eine `--ui-*`/`--ops-*`-Variable in ein Stylesheet zurückkehrt,
- Farbliterale, px-Werte oder DaisyUI in die Tailwind-Konfiguration zurückkehren.

## DaisyUI

Entfernt. Version 5 setzt Tailwind 4 voraus und hat mit Tailwind 3.4 keine
einzige Regel erzeugt; `.btn`, `.badge` und Co. stammen aus
`app/static/css/src/`. Der Build war mit und ohne Plugin bis auf die Token
identisch.
