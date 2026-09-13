type CreateActionKey =
  | "adminFaqDraft"
  | "adminKnowledgeUpload"
  | "adminPromptDraft"
  | "documentFilter"
  | "documentManualUpload"
  | "documentUploadCheck"
  | "employeeCreate"
  | "errorCreate"
  | "errorSuggestion"
  | "handoverCreate"
  | "inventoryMaterialCreate"
  | "machineCreate"
  | "shiftplanGenerate"
  | "taskCreate"
  | "taskSuggestion"
  | "vacationRequest";

export type CreateActionDefinition = {
  readonly key: CreateActionKey;
  readonly title: string;
  readonly description: string;
  readonly primaryLabel: string;
};

const CREATE_ACTION_DEFINITIONS: Record<CreateActionKey, CreateActionDefinition> = {
  adminFaqDraft: {
    key: "adminFaqDraft",
    title: "FAQ-Entwurf erfassen",
    description: "Frage, freigegebene Antwort, Kategorie und Kontext als Entwurf speichern.",
    primaryLabel: "FAQ erfassen"
  },
  adminKnowledgeUpload: {
    key: "adminKnowledgeUpload",
    title: "Wissensdokument hochladen",
    description: "PDF, TXT oder HTML als manuelle Wissensquelle speichern und indexierbar machen.",
    primaryLabel: "Wissen hochladen"
  },
  adminPromptDraft: {
    key: "adminPromptDraft",
    title: "Prompt-Entwurf anlegen",
    description: "System-Prompt, User-Template und Änderungsnotiz als neue Version speichern.",
    primaryLabel: "Prompt anlegen"
  },
  documentFilter: {
    key: "documentFilter",
    title: "Dokumente filtern",
    description: "Nach Aufgabe, Bereich, Maschine oder Datum suchen.",
    primaryLabel: "Filter"
  },
  documentManualUpload: {
    key: "documentManualUpload",
    title: "Handbuch hochladen",
    description: "PDF, TXT oder HTML speichern und für die Suche nutzbar machen.",
    primaryLabel: "Handbuch hochladen"
  },
  documentUploadCheck: {
    key: "documentUploadCheck",
    title: "Upload prüfen",
    description: "HTML- oder TXT-Bericht prüfen, ohne ihn dauerhaft zu speichern.",
    primaryLabel: "Upload prüfen"
  },
  employeeCreate: {
    key: "employeeCreate",
    title: "Mitarbeiter anlegen",
    description: "Stammdaten, Schicht, Team und Qualifikationen erfassen.",
    primaryLabel: "Mitarbeiter anlegen"
  },
  errorCreate: {
    key: "errorCreate",
    title: "Störung erfassen",
    description: "Maschine, Kategorie, Symptome, Ursache, Lösung und Auswirkungen speichern.",
    primaryLabel: "Störung erfassen"
  },
  errorSuggestion: {
    key: "errorSuggestion",
    title: "Aus Beschreibung vorschlagen",
    description: "Freitext in prüfbare Ursache, Lösung und Katalogdaten umwandeln.",
    primaryLabel: "Vorschlag erstellen"
  },
  handoverCreate: {
    key: "handoverCreate",
    title: "Neue Übergabe",
    description: "Bereich, Schicht, Risiken und Folgearbeiten erfassen.",
    primaryLabel: "Neue Übergabe"
  },
  inventoryMaterialCreate: {
    key: "inventoryMaterialCreate",
    title: "Material anlegen",
    description: "Bestand, Wert und Maschinenbezug erfassen.",
    primaryLabel: "Material anlegen"
  },
  machineCreate: {
    key: "machineCreate",
    title: "Maschine anlegen",
    description: "Anlage und Produktionsdaten erfassen.",
    primaryLabel: "Maschine anlegen"
  },
  shiftplanGenerate: {
    key: "shiftplanGenerate",
    title: "Schichtplan generieren",
    description: "Abteilung, Zeitraum, Modell und Maschinen für den neuen Plan festlegen.",
    primaryLabel: "Schichtplan generieren"
  },
  taskCreate: {
    key: "taskCreate",
    title: "Aufgabe anlegen",
    description: "Bereich, Priorität, Status und Fälligkeit setzen.",
    primaryLabel: "Aufgabe anlegen"
  },
  taskSuggestion: {
    key: "taskSuggestion",
    title: "Aus Meldung erstellen",
    description: "Freitext in eine prüfbare Aufgabe umwandeln.",
    primaryLabel: "Aus Meldung erstellen"
  },
  vacationRequest: {
    key: "vacationRequest",
    title: "Urlaub beantragen",
    description: "Zeitraum, Schichtbezug und Vertreter gegen Resturlaub und Teamlage prüfen.",
    primaryLabel: "Urlaub beantragen"
  }
} as const;

/**
 * Return the configured create-action schema for one action key.
 */
export function createActionDefinition(key: CreateActionKey): CreateActionDefinition {
  return CREATE_ACTION_DEFINITIONS[key];
}
