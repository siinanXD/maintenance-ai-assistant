# Design-Token

Quelle der Wahrheit für Farben, Masse und Breakpoints der Anwendung. Wer einen
Wert ändern will, ändert ihn hier — nicht in `tailwind.config.js`, nicht in den
60 CSS-Quelldateien.

## Eine Datei, zwei Ebenen

Alle Token liegen in `tokens.json`, im Single-File-Format von Tokens Studio.
Jedes Token-Set ist ein Schlüssel auf oberster Ebene:

| Set | Inhalt | Wer verweist darauf |
| --- | --- | --- |
| `core` | Primitive Farbwerte, nach Farbton benannt (`color.blue.600`) | nur `semantic` |
| `semantic` | Rollen (`color.action.default`), Masse, Breakpoints | die Anwendung |

Daneben stehen `$themes` und `$metadata`. Das sind Verwaltungsdaten des Plugins
(Theme-Liste, Reihenfolge der Sets), keine Token.

Die Trennung in zwei Sets hat einen Zweck: Ein Rollenname wie
`color.status.critical` bleibt stabil, während sich der Farbwert dahinter
ändert. Der Palettentausch aus Schritt 4 des Werkbank-Briefs ist deshalb eine
Änderung am Set `core` allein.

Aliase nennen den Set-Namen nicht (`{color.blue.600}`, nicht
`{core.color.blue.600}`), weil Tokens Studio die Sets zusammenführt. Der
Generator entpackt die Sets deshalb vor dem Build.

Format ist [DTCG](https://tr.designtokens.org/format/) (`$value`, `$type`).

## Warum eine Datei und nicht ein Ordner

Tokens Studio kann Sets auch als einzelne Dateien in einem Ordner synchronisieren.
Das ist aber ein [Pro-Feature](https://docs.tokens.studio/token-storage/remote-multi-file-sync):
Mit der Free-Version sind so gesyncte Token nur lesbar. Eine einzelne Datei
funktioniert mit Free und mit Pro gleichermassen.

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

## Anschluss an Tokens Studio

Plugins laufen in der Figma-Datei, nicht in den Team-Einstellungen auf figma.com.

1. Die Datei „Maintenance AI — Design System & Redesign" öffnen.
2. Rechtsklick auf die Zeichenfläche → *Plugins* → *Tokens Studio for Figma*.
3. Im Plugin *Settings → Sync providers → Add new → GitHub*.
4. Eintragen:

   | Feld | Wert |
   | --- | --- |
   | Personal Access Token | selbst erzeugen, siehe unten |
   | Repository (owner/repo) | `siinanXD/maintenance-ai-assistant` |
   | Branch | `design/tokens-sync` |
   | Token storage location | `design/tokens/tokens.json` |
   | Base URL | leer lassen |

   Bei *Token storage location* muss der **Dateiname** stehen. Ein reiner
   Ordnerpfad schaltet auf Multi-File-Sync, und der ist Pro.

5. *Save*, danach *Pull from GitHub*. Die Sets `core` und `semantic` erscheinen
   links in der Set-Liste.

**Personal Access Token:** auf github.com unter *Settings → Developer settings →
Personal access tokens → Fine-grained tokens*. Repository access auf dieses eine
Repository beschränken, Berechtigungen *Contents: Read and write* und
*Pull requests: Read and write*. Das Token wird nur im Plugin eingetragen.

Änderungen aus Figma landen per Push auf `design/tokens-sync` und gehen von dort
als Pull Request nach `master`. Vor dem Merge `npm run build:tokens` — der
Drift-Wächter erzwingt es, sonst wird die CI rot.
