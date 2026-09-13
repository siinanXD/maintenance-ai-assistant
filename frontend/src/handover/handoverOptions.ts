type SelectOption = {
  readonly label: string;
  readonly value: string;
};

export const DEPARTMENT_OPTIONS: readonly SelectOption[] = [
  { label: "Produktion", value: "Produktion" },
  { label: "Instandhaltung", value: "Instandhaltung" },
  { label: "Verwaltung", value: "Verwaltung" },
  { label: "IT", value: "IT" },
];

export const SHIFT_OPTIONS: readonly SelectOption[] = [
  { label: "Frühschicht", value: "Frueh" },
  { label: "Spätschicht", value: "Spaet" },
  { label: "Nachtschicht", value: "Nacht" },
];

export const PRODUCTION_STATUS_OPTIONS: readonly SelectOption[] = [
  { label: "Läuft stabil", value: "running" },
  { label: "Reduzierte Leistung", value: "reduced" },
  { label: "Stillstand", value: "stopped" },
  { label: "Qualitätssperre", value: "quality_hold" },
];

export const MACHINE_STATUS_OPTIONS: readonly SelectOption[] = [
  { label: "In Ordnung", value: "ok" },
  { label: "Beobachten", value: "watch" },
  { label: "Wartung erforderlich", value: "maintenance" },
  { label: "Störung aktiv", value: "fault" },
];

export const PROBLEM_CATEGORY_OPTIONS: readonly string[] = [
  "Elektrik",
  "Mechanik",
  "Pneumatik",
  "Hydraulik",
  "SPS/Software",
  "Sensorik",
  "Netzwerk",
  "Material",
  "Qualität",
  "Sicherheit",
  "Organisation",
  "Sonstiges",
];
