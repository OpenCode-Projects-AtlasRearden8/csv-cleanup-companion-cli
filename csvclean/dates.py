"""Friendly date normalization -> ISO 8601 (YYYY-MM-DD).

Built on the standard library only. We accept the formats real-world
CSVs actually contain, and we are upfront about ambiguity: numeric
dates default to US order (month/day), unless the first number is
clearly a day (13-31), in which case we read day/month.
"""

from datetime import date, datetime

_FORMATS = (
    # Unambiguous first
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    # Month-name styles
    "%B %d %Y",
    "%B %d, %Y",
    "%b %d %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%A, %B %d, %Y",
    "%a %b %d, %Y",
    # Excel-ish numeric styles (month/day, US order)
    "%m/%d/%Y",
    "%m/%d/%y",
    "%m-%d-%Y",
    "%m.%d.%Y",
    # Day/month (rest of the world)
    "%d/%m/%Y",
    "%d-%m-%Y",
)


def try_parse_date(value):
    """Best-effort date parse. Returns a date or None."""
    text = value.strip()
    if not text:
        return None
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return _parse_numeric_ambiguity(text)


def _parse_numeric_ambiguity(text):
    parts = text.replace("/", "-").replace(".", "-").split("-")
    if len(parts) != 3:
        return None
    a, b, y = parts
    if not (a.isdigit() and b.isdigit() and y.isdigit()):
        return None
    if len(y) == 2:
        y = ("20" if int(y) <= 68 else "19") + y
    if len(y) != 4:
        return None
    ai, bi, yi = int(a), int(b), int(y)
    if not (1 <= yi <= 9999):
        return None
    try:
        if ai > 12:  # day clearly first
            return date(yi, bi, ai)
        if bi > 12:  # month clearly first
            return date(yi, ai, bi)
        # Default to US order, like most software users expect.
        return date(yi, ai, bi)
    except ValueError:
        return None


def to_iso(value):
    """Return Y-M-D string, or None if it is not a recognizable date."""
    parsed = try_parse_date(value)
    if parsed is None:
        return None
    return parsed.strftime("%Y-%m-%d")


def normalize_date_column(values):
    """Convert values to ISO; returns (new_values, fixed, skipped_values).

    Empty cells are left empty and never counted as skipped.
    """
    new_values, fixed, skipped = [], 0, []
    for value in values:
        if str(value).strip() == "":
            new_values.append(value)
            continue
        iso = to_iso(value)
        if iso is None:
            new_values.append(value)
            skipped.append(value)
        else:
            new_values.append(iso)
            if iso != value.strip():
                fixed += 1
    return new_values, fixed, skipped
