# Design-Token

`tokens.json` ist die Quelle, aus der die Anwendung Farben, Masse und
Breakpoints bezieht. Werte ändert man hier oder in Figma, nie in
`tailwind.config.js` oder in den 60 CSS-Quelldateien.

## Woher die Werte kommen

Gestalterische Quelle ist die Figma-Datei **„Maintenance AI — Design System &
Redesign"**. Dort werden Farben, Radien und Schriften entworfen und auf allen
14 Screens hell und dunkel geprüft.

Übertragen werden die Werte über die Figma-MCP-Anbindung von Claude Code, die
die Variablen direkt aus der Datei liest. Dafür ist kein Figma-Plugin, kein
GitHub-Token und kein eigener Sync-Branch nötig.

Stand 13.09.2026: Die Figma-Datei zeigt bereits die Werkbank-Palette,
`tokens.json` noch die alte. Die Übernahme ist der nächste Schritt.

## Eine Datei, zwei Ebenen

Jedes Token-Set ist ein Schlüssel auf oberster Ebene von `tokens.json`:

| Set | Inhalt | Wer verweist darauf |
| --- | --- | --- |
| `core` | Primitive Farbwerte, nach Farbton benannt (`color.blue.600`) | nur `semantic` |
| `semantic` | Rollen (`color.action.default`), Masse, Breakpoints | die Anwendung |

Schlüssel mit `$` am Anfang (`$themes`, `$metadata`) sind Metadaten, keine
Token.

Die Trennung hat einen Zweck: Ein Rollenname wie `color.status.critical` bleibt
stabil, während sich der Farbwert dahinter ändert.

Aliase nennen den Set-Namen nicht (`{color.blue.600}`, nicht
`{core.color.blue.600}`), weil beide Sets gemeinsam aufgelöst werden. Der
Generator entpackt sie deshalb vor dem Build in einzelne Dateien.

Format ist [DTCG](https://tr.designtokens.org/format/) (`$value`, `$type`).

## Erzeugte Dateien

`npm run build:tokens` schreibt aus `tokens.json`:

| Ziel | Inhalt | Verbraucher |
| --- | --- | --- |
| `app/static/css/src/00-shell-tokens.css` | CSS-Custom-Properties der semantischen Ebene | `base.html`, `99-shell-layout.css`, künftig die Feature-CSS |
| `design/tokens/generated/tailwind.cjs` | Tailwind-Theme und DaisyUI-Palette | `tailwind.config.js` |

Beide sind eingecheckt, weil die CI nur `npm --prefix frontend ci` ausführt und
den Generator dort nicht laufen lässt. `npm run build:css` ruft den Token-Build
automatisch vorher auf.

Die Primitive aus `core` verlassen den Generator nicht. In der Anwendung soll
`--color-action-default` stehen, nie `--color-blue-600`.

## Was der Drift-Wächter prüft

`tests/test_design_tokens.py` leitet die erwartete Ausgabe in reinem Python neu
her und läuft damit in der CI mit. Er schlägt an, wenn

- eine Tokenänderung nicht neu gebaut wurde,
- eine DaisyUI-Rolle nicht mehr zu ihrem semantischen Token passt,
- ein Farbliteral oder ein `px`-Wert nach `tailwind.config.js` zurückwandert,
- die Namen verschwinden, die `base.html` und `99-shell-layout.css` lesen
  (`--sidebar-width`, `--sidebar-width-collapsed`, `--topbar-height`),
- `tokens.json` die Sets `core` und `semantic` verliert oder neben ihr wieder
  einzelne Set-Dateien auftauchen.

## Noch nicht übernommen

`radius` und `elevation` stehen als CSS-Custom-Properties bereit, sind aber
bewusst **nicht** in Tailwinds Theme gehängt: das würde Tailwinds Standardskalen
ersetzen und jedes vorhandene `rounded-*` und `shadow-*` verändern. Sie lösen in
Schritt 4 bis 6 die 295 Freihand-Radien und 140 Freihand-Schatten ab.

`space` ist deckungsgleich mit Tailwinds Standardskala (Basis 4 px) und braucht
deshalb keinen Override.
