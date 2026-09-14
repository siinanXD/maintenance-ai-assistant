# Styles

`npm run build:css` fügt alle Dateien unter `src/` nach Pfad sortiert zusammen
und erzeugt daraus mit Tailwind `output.css`. Die Reihenfolge der Ordner ist die
Kaskade:

| Ordner | Inhalt | Regel |
| --- | --- | --- |
| `src/00-foundation/` | Schriften und Design-Token (beide erzeugt) | nicht von Hand ändern: `npm run build:tokens`, `npm run build:fonts` |
| `src/10-legacy/` | gemeinsame ältere Bausteine (Karten, Buttons, Formulare, Tabellen, Layout) in ihrer ursprünglichen Reihenfolge | nur löschen oder durch `20-components/` ersetzen |
| `src/15-pages/` | Seitenstile, eine Datei je Seite oder Shell-Bereich (`tasks.css`, `incidents.css`, `admin-ai.css`, `shell.css` …) | Änderungen an einer Seite gehören in ihre Datei |
| `src/20-components/` | neue Bausteine auf Token-Basis (Seitenkopf, Kennzahlen, Topbar, Login, Anhänge, Aufträge, Prüfungen) | neue Stile gehören hierher, eine Datei je Baustein |
| `src/90-overrides/` | Token-Farben über älteren festen Farbwerten, Shell-Layout | wird kleiner, je mehr Seiten auf Token umgestellt sind |

Alle Stile lesen die Design-Token (`var(--color-…)`, `var(--space-…)`,
`var(--radius-…)`) direkt. Die früheren `--ui-*`- und `--ops-*`-Variablen gibt
es nicht mehr; `tests/test_design_tokens.py` verhindert, dass sie zurückkehren.

## Herkunft von 10-legacy und 15-pages

Beide Ordner stammen aus einem über viele Iterationen gewachsenen Stylesheet.
Spätere Regeln überschreiben frühere mit gleicher Spezifität, deshalb stehen
die Regeln innerhalb jeder Datei in ihrer ursprünglichen Reihenfolge. Bereinigt
ist bereits:

- Deklarationen, die eine spätere Regel mit identischem Selektor immer
  überschreibt,
- Selektoren, deren Klassen, IDs oder `data-*`-Attribute nirgends mehr vorkommen,
- die Aufteilung nach Seiten: eine Regel liegt in `15-pages/<seite>.css`, wenn
  sie nur Klassen dieser Seite (plus gemeinsame Bausteine) anspricht.

Jeder Umbau wurde mit berechneten Styles aller Seiten (Desktop, Tablet, Handy) vorher und nachher verglichen.

## Eine Seite umbauen

1. Die Regeln aus `15-pages/<seite>.css` auf Token und die Bausteine aus
   `20-components/` umstellen, feste Farbwerte ersetzen.
2. Die Einträge dieser Seite in `90-overrides/token-overrides.css` löschen.
3. Seite im Browser prüfen, `npm run build:css`, Screenshots aktualisieren.
