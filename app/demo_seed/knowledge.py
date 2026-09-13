"""Static demo seed definitions."""

MAINTENANCE_PLAN_DEFINITIONS = [
    (
        "Hydraulikpresse 03 - Hydraulikdruck und Leckagecheck",
        "Druckhaltepruefung bei 180 bar, Schlauchpakete sichtpruefen, "
        "Dichtungssatz und O-Ring-Bestand vor Stillstand kontrollieren.",
        30,
        2,
        "urgent",
        "Instandhaltung",
        "hydraulikpresse-03",
        True,
    ),
    (
        "Kompressorstation 07 - Druckluftqualitaet und Filter",
        "Taupunkt, Kondensatableiter und Druckluftfilter G1/2 pruefen. "
        "Bei Taupunkt > 3 Grad C Trockner reinigen und Leckagesuche starten.",
        14,
        4,
        "soon",
        "Instandhaltung",
        "kompressorstation-07",
        True,
    ),
    (
        "Montagelinie 05 - Sicherheitskreis und Sensorik",
        "Not-Halt, Tuerkontakte, induktive M8 Sensoren und Verriegelungen testen. "
        "Abweichungen direkt im Schichtbuch dokumentieren.",
        90,
        8,
        "normal",
        "Instandhaltung",
        "montagelinie-05",
        True,
    ),
    (
        "Roboterzelle 09 - Greifer, Vakuum und TCP",
        "Sauger, Vakuumkreis und TCP nach Kollisionen pruefen. "
        "Haltekraft je Station messen und Greiferfinger sichtpruefen.",
        21,
        1,
        "soon",
        "Produktion",
        "roboterzelle-09",
        True,
    ),
    (
        "Pruefstand 08 - Kontaktleisten und Kalibrierung",
        "Kontaktwiderstand der Adapter messen, Kalibrierstatus pruefen und "
        "NIO-Haeufungen mit QS abgleichen.",
        60,
        12,
        "normal",
        "Produktion",
        "prufstand-08",
        True,
    ),
]

# (title, legal basis, scope, interval days, due in days, department, machine key,
#  last execution: (days ago, performed by, result, notes) or None)
INSPECTION_PLAN_DEFINITIONS = [
    (
        "Prüfung elektrischer Anlagen und Betriebsmittel",
        "DGUV Vorschrift 3",
        "Isolationswiderstand, Schutzleiter und RCD-Auslösezeit messen; Prüfplakette erneuern.",
        365,
        -6,
        "Instandhaltung",
        "hydraulikpresse-03",
        (371, "Elektro Brandt GmbH", "passed", "Prüfprotokoll E-2025-0412"),
    ),
    (
        "Druckbehälterprüfung Kompressor",
        "BetrSichV § 16",
        "Äußere Prüfung Druckbehälter, Sicherheitsventil anlüften, Kondensatablass prüfen.",
        730,
        21,
        "Instandhaltung",
        "kompressorstation-07",
        (709, "TÜV Süd Industrie Service", "defects", "Kondensatableiter undicht, getauscht"),
    ),
    (
        "Sicherheitsfunktionen Roboterzelle",
        "DIN EN ISO 10218-2",
        "Schutztür-Verriegelung, Lichtvorhang und Not-Halt unter Last testen.",
        182,
        48,
        "Produktion",
        "roboterzelle-09",
        (134, "Sicherheitsfachkraft Keller", "passed", "Alle Funktionen i. O."),
    ),
    (
        "Leitern und Tritte",
        "DGUV Information 208-016",
        "Sichtprüfung Holme, Sprossen, Gelenke und Spreizsicherung; Prüfliste aktualisieren.",
        365,
        140,
        "Instandhaltung",
        None,
        (225, "Meister Wagner", "passed", "12 Leitern geprüft, 1 ausgesondert"),
    ),
]

ACTIVE_ERROR_STATES = {
    ("Instandhaltung", "E-101"): {
        "status": "open",
        "severity": "critical",
        "cause_category": "Sensorik",
        "impact": "Linie muss überwacht laufen, Ausschussrisiko erhöht.",
        "downtime_minutes": 35,
        "production_loss_minutes": 50,
        "repeat_count": 2,
        "seen_hours": 2,
    },
    ("Instandhaltung", "E-103"): {
        "status": "in_progress",
        "severity": "high",
        "cause_category": "Hydraulik",
        "impact": "Taktzeit reduziert, Wartungsfenster erforderlich.",
        "downtime_minutes": 20,
        "production_loss_minutes": 30,
        "repeat_count": 1,
        "seen_hours": 5,
    },
    ("Produktion", "E-104"): {
        "status": "open",
        "severity": "high",
        "cause_category": "Mechanik",
        "impact": "Qualitätsfreigabe ausstehend.",
        "downtime_minutes": 0,
        "production_loss_minutes": 15,
        "repeat_count": 1,
        "seen_hours": 1,
    },
}

MANUAL_DEFINITIONS = [
    (
        "hydraulikpresse-03",
        "Instandhaltung",
        "hydraulikpresse-03-betriebsanweisung.txt",
        "Betriebsanweisung Hydraulikpresse 03",
        (
            "Maschine: Hydraulikpresse 03\n"
            "Fehlercodes: INS-E-103, INS-E-112\n"
            "Hydraulikdruckverlust: Anlage sichern, Druck abbauen, Lecktest "
            "mit Spruehkreide durchfuehren, Filterzustand pruefen und "
            "Dichtungssatz Presse bereitlegen.\n"
            "Freigabe erst nach 10 Minuten Druckhaltepruefung ohne sichtbare "
            "Leckage und dokumentiertem Oelstand.\n"
        ),
    ),
    (
        "spritzgussanlage-04",
        "Instandhaltung",
        "spritzgussanlage-04-heizzonen.txt",
        "Servicehinweis Spritzgussanlage 04",
        (
            "Maschine: Spritzgussanlage 04\n"
            "Fehlercodes: INS-E-104, PRO-E-118\n"
            "Bei Temperaturabweichung Heizzone einzeln freischalten, "
            "Heizkabel 230 V mit Messzange pruefen und Kuehlwasserdurchfluss "
            "kontrollieren. Material PA6 erst nach stabiler Zone freigeben.\n"
        ),
    ),
    (
        "kompressorstation-07",
        "Instandhaltung",
        "kompressorstation-07-druckluft.txt",
        "Wartungsanweisung Kompressorstation 07",
        (
            "Maschine: Kompressorstation 07\n"
            "Fehlercode: INS-E-116\n"
            "Druckluftqualitaet: Taupunkt messen, Kondensatableiter ausloesen, "
            "Druckluftfilter G1/2 wechseln und Leckagen im Ringnetz markieren.\n"
        ),
    ),
]

SHIFT_HANDOVER_DEFINITIONS = [
    (
        "Instandhaltung",
        0,
        "Frueh",
        "open",
        "thomas.hoffmann",
        "Hydraulikpresse 03 wegen Druckverlust nur im reduzierten Takt betreiben.",
        "Task Hydraulikpresse 03 - Dichtigkeitspruefung laeuft; Material Dichtungssatz fehlt.",
        "Hydraulikpresse 03: Oelstand stabil, aber Leckage an Ventilblock V3 wahrscheinlich.",
        "Spaetschicht soll INS-E-103 pruefen und O-Ring-Satz aus Lager nachfordern.",
    ),
    (
        "Produktion",
        0,
        "Spaet",
        "open",
        "ayse.demir",
        "Spritzgussanlage 04 hatte drei Temperaturwarnungen in Heizzone 3.",
        "Granulat PA6 ist nachgefuellt; Heizkabel-Tausch fuer Stillstand eingeplant.",
        "Spritzgussanlage 04: Rezept W44 stabil, Ausschussquote leicht erhoeht.",
        "Nachtschicht soll erste 20 Teile messen und QS bei Drift informieren.",
    ),
    (
        "Verwaltung",
        -1,
        "Frueh",
        "completed",
        "petra.weiss",
        "Kritische Ersatzteile fuer Hydraulikpresse 03 und Laserbeschrifter 10 priorisiert.",
        "Dichtungssatz Presse ist Bestand 0; Parker-Bestellung eskaliert.",
        "Verpackungsanlage 06 Material fuer Auftrag 5021 bereitgestellt.",
        "Wareneingang soll Laser-Schutzglas direkt an Instandhaltung melden.",
    ),
]

TRAINING_DEFINITIONS = [
    (
        "Demo: Hydraulikdruckverlust strukturiert beantworten",
        "Wie loese ich Hydraulikdruckverlust an Hydraulikpresse 03?",
        (
            "Nur mit Quellen antworten. Prioritaet haben Fehler INS-E-103, "
            "Manual Hydraulikpresse 03 und offene Tasks. Immer erst Anlage "
            "sichern, Druck abbauen, Lecktest, Filter und Ventilblock pruefen."
        ),
        "Hydraulikpresse 03, Druck faellt ab, INS-E-103, Dichtungssatz Presse, O-Ring",
        "demo_ai",
        "Instandhaltung",
        95,
        True,
    ),
    (
        "Demo: Kritische Maschine identifizieren",
        "Welche Maschine ist aktuell kritisch?",
        (
            "Kritisch sind Maschinen mit critical/high Criticality, laufenden "
            "urgent Tasks, aktuellen Schichtuebergaben oder fehlenden Ersatzteilen."
        ),
        "kritische Maschine, urgent Tasks, Hydraulikpresse 03, Kompressorstation 07",
        "demo_ai",
        "Produktion",
        85,
        True,
    ),
    (
        "Demo: Ersatzteilrisiko erklaeren",
        "Welche Ersatzteile blockieren Wartung an Hydraulikpresse 03?",
        (
            "Nenne nur sichtbare Lagerpositionen. Dichtungssatz Presse und "
            "O-Ring-Satz sind fuer Hydraulikdruckverlust relevant; Bestand, "
            "Mindestbestand und Lieferzeit erwaehnen."
        ),
        "Ersatzteil, Mindestbestand, Dichtungssatz Presse, O-Ring-Satz, Hydraulikpresse",
        "demo_ai",
        "Verwaltung",
        80,
        True,
    ),
    (
        "Demo: Schichtuebergabe zusammenfassen",
        "Was wurde in der letzten Schicht zu Spritzgussanlage 04 gemeldet?",
        (
            "Schichtuebergaben knapp zusammenfassen und offene naechste Schritte "
            "aus next_notes nennen. Keine Mitarbeitenden-Details ausgeben."
        ),
        "Schichtuebergabe, Spritzgussanlage 04, Heizzone 3, Nachtschicht, QS",
        "demo_ai",
        "Produktion",
        78,
        True,
    ),
]


# ---------------------------------------------------------------------------
# Öffentliche Seeding-Funktion
# ---------------------------------------------------------------------------
