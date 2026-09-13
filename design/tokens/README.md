# Design-Token

Quelle der Wahrheit für Farben, Masse und Breakpoints der Anwendung. Wer einen
Wert ändern will, ändert ihn hier — nicht in `tailwind.config.js`, nicht in den
60 CSS-Quelldateien.

## Zwei Ebenen

| Datei | Inhalt | Wer verweist darauf |
| --- | --- | --- |
| `core.json` | Primitive Farbwerte, nach Farbton benannt (`color.blue.600`) | nur `semantic.json` |
| `semantic.json` | Rollen (`color.action.default`), Masse, Breakpoints | die Anwendung |

Die Trennung hat einen Zweck: Ein Rollenname wie `color.status.critical` bleibt
stabil, während sich der Farbwert dahinter ändert. Der Palettentausch aus
Schritt 4 des Werkbank-Briefs ist deshalb eine Änderung an `core.json` allein.

Format ist [DTCG](https://tr.designtokens.org/format/) (`$value`, `$type`) —
dasselbe, das Tokens Studio exportiert und importiert.

## Erzeugte Dateien

`npm run build:tokens` schreibt aus den beiden Quellen:

| Ziel | Inhalt | Verbraucher |
| --- | --- | --- |
| `app/static/css/src/00-shell-tokens.css` | CSS-Custom-Properties der semantischen Ebene | `base.html`, `99-shell-layout.css`, künftig die Feature-CSS |
| `design/tokens/generated/tailwind.cjs` | Tailwind-Theme und DaisyUI-Palette | `tailwind.config.js` |

Beide sind eingecheckt, weil die CI nur `npm --prefix frontend ci` ausführt und
den Generator dort nicht laufen lässt. `npm run build:css` ruft den Token-Build
automatisch vorher auf.

Die Primitive aus `core.json` verlassen den Generator nicht. In der Anwendung
soll `--color-action-default` stehen, nie `--color-blue-600`.

## Was der Drift-Wächter prüft

`tests/test_design_tokens.py` leitet die erwartete Ausgabe in reinem Python neu
her und läuft damit in der CI mit. Er schlägt an, wenn

- eine Tokenänderung nicht neu gebaut wurde,
- eine DaisyUI-Rolle nicht mehr zu ihrem semantischen Token passt,
- ein Farbliteral oder ein `px`-Wert nach `tailwind.config.js` zurückwandert,
- die Namen verschwinden, die `base.html` und `99-shell-layout.css` lesen
  (`--sidebar-width`, `--sidebar-width-collapsed`, `--topbar-height`).

## Noch nicht übernommen

`radius` und `elevation` stehen als CSS-Custom-Properties bereit, sind aber
bewusst **nicht** in Tailwinds Theme gehängt: das würde Tailwinds Standardskalen
ersetzen und jedes vorhandene `rounded-*` und `shadow-*` verändern. Sie lösen in
Schritt 4 bis 6 die 295 Freihand-Radien und 140 Freihand-Schatten ab.

`space` ist deckungsgleich mit Tailwinds Standardskala (Basis 4 px) und braucht
deshalb keinen Override.

## Anschluss an Tokens Studio

Noch offen, weil er im Figma-File eingerichtet werden muss:

1. In Figma das Plugin **Tokens Studio** öffnen, *Settings → Sync → GitHub*.
2. Repository `siinanXD/maintenance-ai-assistant`, Branch `design/tokens`,
   Token-Pfad `design/tokens`.
3. *Import* zieht `core.json` und `semantic.json` als zwei Token-Sets herein.
4. Änderungen in Figma gehen als Pull Request zurück; `npm run build:tokens`
   erzeugt daraus die beiden Zieldateien, der Drift-Wächter hält sie ehrlich.

Bis dahin sind die JSON-Dateien von Hand gepflegt. Am Vertrag ändert das nichts:
Wer an ihnen dreht, muss neu bauen, sonst wird die CI rot.
