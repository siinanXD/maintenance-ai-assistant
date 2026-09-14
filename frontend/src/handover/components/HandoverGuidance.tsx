import { type ReactNode } from "react";

const CHECKLIST_ITEMS = [
  "Schicht und Bereich auswählen",
  "Maschine und Status festhalten",
  "Probleme, Ursache und Maßnahme trennen",
  "Sicherheit und Material markieren",
  "Folgepunkte an nächste Schicht übergeben",
] as const;

/**
 * Render the static handover guidance checklist.
 */
export function HandoverGuidance(): ReactNode {
  return (
    <aside className="handover-guidance-panel app-card">
      <h2>Checkliste</h2>
      <ol className="handover-checklist">
        {CHECKLIST_ITEMS.map((item, index) => (
          <li key={item}>
            <span>{index + 1}</span>
            <strong>{item}</strong>
          </li>
        ))}
      </ol>
    </aside>
  );
}
