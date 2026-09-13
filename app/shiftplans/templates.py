"""German shift model templates for workforce planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from unicodedata import normalize


@dataclass(frozen=True)
class ShiftWindow:
    """A named work shift with a stable key and time window."""

    key: str
    display_name: str
    start_time: str
    end_time: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable representation of the shift window."""
        return {
            "key": self.key,
            "name": self.display_name,
            "label": self.display_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


@dataclass(frozen=True)
class ShiftTemplate:
    """Configuration for one supported German shift model."""

    key: str
    display_name: str
    description: str
    shifts: tuple[ShiftWindow, ...]
    team_count: int
    weekend_operation: bool
    rotation_direction: str
    weekly_hours_target: float
    max_consecutive_nights: int
    recommended_rest_hours: float
    active_weekdays: tuple[int, ...]

    @property
    def shift_times(self) -> dict[str, tuple[str, str]]:
        """Return shift time windows keyed by shift name."""
        return {shift.key: (shift.start_time, shift.end_time) for shift in self.shifts}

    @property
    def rotation(self) -> tuple[str, ...]:
        """Return the forward rotation order for this template."""
        return tuple(shift.key for shift in self.shifts)

    def is_active_on(self, work_date: date) -> bool:
        """Return whether this template plans work on a date."""
        return work_date.weekday() in self.active_weekdays

    def to_dict(self) -> dict[str, object]:
        """Return API-ready shift model metadata."""
        return {
            "key": self.key,
            "name": self.display_name,
            "display_name": self.display_name,
            "description": self.description,
            "shifts": [shift.to_dict() for shift in self.shifts],
            "shift_times": {
                key: {"start_time": value[0], "end_time": value[1]}
                for key, value in self.shift_times.items()
            },
            "team_count": self.team_count,
            "weekend_operation": self.weekend_operation,
            "rotation_direction": self.rotation_direction,
            "weekly_hours_target": self.weekly_hours_target,
            "max_consecutive_nights": self.max_consecutive_nights,
            "recommended_rest_hours": self.recommended_rest_hours,
            "active_weekdays": list(self.active_weekdays),
        }


FRUEH_SHIFT = ShiftWindow("Frueh", "Fruehschicht", "06:00", "14:00")
SPAET_SHIFT = ShiftWindow("Spaet", "Spaetschicht", "14:00", "22:00")
NACHT_SHIFT = ShiftWindow("Nacht", "Nachtschicht", "22:00", "06:00")

WEEKDAYS_MO_FR = (0, 1, 2, 3, 4)
WEEKDAYS_MO_SA = (0, 1, 2, 3, 4, 5)
WEEKDAYS_247 = (0, 1, 2, 3, 4, 5, 6)

SHIFT_TEMPLATES: dict[str, ShiftTemplate] = {
    "one_shift": ShiftTemplate(
        key="one_shift",
        display_name="1-Schicht Tagschicht",
        description="Eine Tagschicht Montag bis Freitag.",
        shifts=(FRUEH_SHIFT,),
        team_count=1,
        weekend_operation=False,
        rotation_direction="fixed",
        weekly_hours_target=40.0,
        max_consecutive_nights=0,
        recommended_rest_hours=11.0,
        active_weekdays=WEEKDAYS_MO_FR,
    ),
    "two_shift": ShiftTemplate(
        key="two_shift",
        display_name="2-Schicht Frueh/Spaet",
        description="Frueh- und Spaetschicht Montag bis Freitag.",
        shifts=(FRUEH_SHIFT, SPAET_SHIFT),
        team_count=2,
        weekend_operation=False,
        rotation_direction="forward",
        weekly_hours_target=40.0,
        max_consecutive_nights=0,
        recommended_rest_hours=11.0,
        active_weekdays=WEEKDAYS_MO_FR,
    ),
    "three_shift": ShiftTemplate(
        key="three_shift",
        display_name="3-Schicht Frueh/Spaet/Nacht",
        description="Frueh-, Spaet- und Nachtschicht Montag bis Freitag.",
        shifts=(FRUEH_SHIFT, SPAET_SHIFT, NACHT_SHIFT),
        team_count=3,
        weekend_operation=False,
        rotation_direction="forward",
        weekly_hours_target=40.0,
        max_consecutive_nights=3,
        recommended_rest_hours=11.0,
        active_weekdays=WEEKDAYS_MO_FR,
    ),
    "teilkonti": ShiftTemplate(
        key="teilkonti",
        display_name="Teilkonti 3-Schicht Mo-Sa",
        description="Drei Schichten Montag bis Samstag.",
        shifts=(FRUEH_SHIFT, SPAET_SHIFT, NACHT_SHIFT),
        team_count=3,
        weekend_operation=True,
        rotation_direction="forward",
        weekly_hours_target=38.0,
        max_consecutive_nights=3,
        recommended_rest_hours=11.0,
        active_weekdays=WEEKDAYS_MO_SA,
    ),
    "vollkonti_4": ShiftTemplate(
        key="vollkonti_4",
        display_name="Vollkonti 4-Schicht 24/7",
        description="Kontinuierlicher 24/7-Betrieb mit vier Teams.",
        shifts=(FRUEH_SHIFT, SPAET_SHIFT, NACHT_SHIFT),
        team_count=4,
        weekend_operation=True,
        rotation_direction="forward",
        weekly_hours_target=36.0,
        max_consecutive_nights=3,
        recommended_rest_hours=11.0,
        active_weekdays=WEEKDAYS_247,
    ),
    "vollkonti_5": ShiftTemplate(
        key="vollkonti_5",
        display_name="Vollkonti 5-Schicht 24/7",
        description="Kontinuierlicher 24/7-Betrieb mit fuenf Teams.",
        shifts=(FRUEH_SHIFT, SPAET_SHIFT, NACHT_SHIFT),
        team_count=5,
        weekend_operation=True,
        rotation_direction="forward",
        weekly_hours_target=33.6,
        max_consecutive_nights=3,
        recommended_rest_hours=11.0,
        active_weekdays=WEEKDAYS_247,
    ),
}

SHIFT_TEMPLATE_ALIASES = {
    "1": "one_shift",
    "1 schicht": "one_shift",
    "1-schicht": "one_shift",
    "one shift": "one_shift",
    "one_shift_day": "one_shift",
    "one shift day": "one_shift",
    "tagschicht": "one_shift",
    "2": "two_shift",
    "2 schicht": "two_shift",
    "2-schicht": "two_shift",
    "two_shift": "two_shift",
    "zweischicht": "two_shift",
    "frueh spaet": "two_shift",
    "3": "three_shift",
    "3 schicht": "three_shift",
    "3-schicht": "three_shift",
    "three_shift": "three_shift",
    "dreischicht": "three_shift",
    "nacht": "three_shift",
    "teilkonti": "teilkonti",
    "teilkonti 3 schicht": "teilkonti",
    "teilkonti 3-schicht": "teilkonti",
    "teilkonti_3_shift_mo_sa": "teilkonti",
    "teilkonti 3 shift mo sa": "teilkonti",
    "vollkonti": "vollkonti_4",
    "vollkonti 4": "vollkonti_4",
    "vollkonti 4 schicht": "vollkonti_4",
    "vollkonti 4-schicht": "vollkonti_4",
    "vollkonti_4_shift_247": "vollkonti_4",
    "vollkonti 4 shift 247": "vollkonti_4",
    "4 schicht": "vollkonti_4",
    "4-schicht": "vollkonti_4",
    "vollkonti 5": "vollkonti_5",
    "vollkonti 5 schicht": "vollkonti_5",
    "vollkonti 5-schicht": "vollkonti_5",
    "vollkonti_5_shift_247": "vollkonti_5",
    "vollkonti 5 shift 247": "vollkonti_5",
    "5 schicht": "vollkonti_5",
    "5-schicht": "vollkonti_5",
}


def list_shift_templates() -> list[ShiftTemplate]:
    """Return all supported shift templates in stable order."""
    return list(SHIFT_TEMPLATES.values())


def get_shift_template(key: str) -> ShiftTemplate:
    """Return a shift template for a canonical key."""
    try:
        return SHIFT_TEMPLATES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown shift template: {key}") from exc


def get_shift_model_template(key: str) -> ShiftTemplate:
    """Return a shift model template for compatibility imports."""
    return get_shift_template(resolve_shift_template(key).key)


def resolve_shift_template(value: object) -> ShiftTemplate:
    """Resolve a canonical template from a key, alias, or legacy rhythm."""
    if isinstance(value, ShiftTemplate):
        return value
    raw_value = str(value or "").strip()
    if raw_value in SHIFT_TEMPLATES:
        return SHIFT_TEMPLATES[raw_value]
    normalized = normalize_template_value(value)
    if not normalized:
        return SHIFT_TEMPLATES["two_shift"]
    if normalized in SHIFT_TEMPLATES:
        return SHIFT_TEMPLATES[normalized]
    if normalized in SHIFT_TEMPLATE_ALIASES:
        return SHIFT_TEMPLATES[SHIFT_TEMPLATE_ALIASES[normalized]]
    if "teilkonti" in normalized:
        return SHIFT_TEMPLATES["teilkonti"]
    if "vollkonti" in normalized and "5" in normalized:
        return SHIFT_TEMPLATES["vollkonti_5"]
    if "vollkonti" in normalized or "4" in normalized:
        return SHIFT_TEMPLATES["vollkonti_4"]
    if "nacht" in normalized or "3" in normalized:
        return SHIFT_TEMPLATES["three_shift"]
    if "tag" in normalized or "1" in normalized:
        return SHIFT_TEMPLATES["one_shift"]
    return SHIFT_TEMPLATES["two_shift"]


def normalize_template_value(value: object) -> str:
    """Normalize user-provided shift template values for matching."""
    text = str(value or "").strip().lower()
    text = normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    for old, new in {
        "_": " ",
        "-": " ",
        "/": " ",
        "\\": " ",
        "rhythmus": "",
    }.items():
        text = text.replace(old, new)
    return " ".join(text.split())
