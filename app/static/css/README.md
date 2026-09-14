# Styles

`npm run build:css` fügt alle Dateien unter `src/` nach Pfad sortiert zusammen
und erzeugt daraus mit Tailwind `output.css`. Die Reihenfolge der Ordner ist die
Kaskade:

| Ordner | Inhalt | Regel |
| --- | --- | --- |
| `src/00-foundation/` | Schriften und Design-Token (beide erzeugt) | nicht von Hand ändern: `npm run build:tokens`, `npm run build:fonts` |
| `src/10-legacy/` | gewachsene Seitenstile in ihrer ursprünglichen Reihenfolge | nur löschen oder auf Token umstellen, nichts Neues hinzufügen |
| `src/20-components/` | neue Bausteine auf Token-Basis (Seitenkopf, Kennzahlen, Topbar, Login, Anhänge, Aufträge, Prüfungen) | neue Stile gehören hierher, eine Datei je Baustein |
| `src/90-overrides/` | Brücke von alten `--ui-*`-Variablen auf Token, Shell-Layout | wird kleiner, je mehr Legacy wegfällt |

## Legacy

`10-legacy/` ist über viele Iterationen entstanden. Die Dateien sind nach
ihrem überwiegenden Inhalt benannt, aber nicht nach Seiten sortiert: Spätere
Regeln überschreiben frühere mit gleicher Spezifität, deshalb bleibt die
Reihenfolge erhalten. Bereinigt ist bereits:

- Deklarationen, die eine spätere Regel mit identischem Selektor immer
  überschreibt,
- Selektoren, deren Klassen, IDs oder `data-*`-Attribute in keinem Template,
  Skript oder React-Modul mehr vorkommen.

Beim Umstellen einer Seite auf `20-components/` die zugehörigen Legacy-Regeln
löschen und `output.css` vorher und nachher vergleichen.
