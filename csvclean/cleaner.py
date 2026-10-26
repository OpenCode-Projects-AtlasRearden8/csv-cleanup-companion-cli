"""The cleaning pipeline: trim, case, rename, split, merge, dates, dupes, checks."""

from csvclean.dates import normalize_date_column
from csvclean.duplicates import find_near_duplicates

CASE_MODES = ("lower", "upper", "title")


def _cell_at(row, index):
    return row[index] if 0 <= index < len(row) else ""


def rename_with_mapping(headers, mapping):
    """Rename headers using the mapping. Mapping keys are matched
    case-insensitively; unmatched keys are reported back."""
    lower_lookup = {h.strip().lower(): h for h in headers}
    new_headers = list(headers)
    used_keys = set()
    for key, value in mapping.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            continue
        original = lower_lookup.get(key.strip().lower())
        if original is None:
            continue
        used_keys.add(key)
        new_headers[headers.index(original)] = value.strip()
    missed = [k for k in mapping if k not in used_keys]
    return new_headers, missed


def apply_case(headers, rows, instructions):
    """Apply case modes. instructions is a list of (mode, column_or_None).

    column_or_None=None means "every column". Columns are matched after
    any renaming, so naming here must reflect the current headers.
    """
    fixers = {"lower": str.lower, "upper": str.upper, "title": str.title}
    # Pre-compute the column indices we will touch, mode by mode.
    planned = []
    for mode, target in instructions:
        if mode not in fixers:
            raise ValueError(f"Unknown case mode: {mode!r}")
        if target is None:
            planned.extend((fixers[mode], i) for i in range(len(headers)))
        else:
            idx = _require_column(headers, target)
            planned.append((fixers[mode], idx))
    touched_columns = {idx for _, idx in planned}
    new_rows = []
    for row in rows:
        new_row = list(row)
        for fix, idx in planned:
            new_row[idx] = fix(_cell_at(row, idx))
        new_rows.append(new_row)
    return new_rows, len(touched_columns), len(rows)


def trim_headers_and_cells(headers, rows):
    """Strip stray whitespace from headers and every cell."""
    new_headers = [str(h).strip() for h in headers]
    new_rows = []
    changed = 0
    for row in rows:
        new_row = []
        for cell in row:
            stripped = cell.strip()
            if stripped != cell:
                changed += 1
            new_row.append(stripped)
        new_rows.append(new_row)
    return new_headers, new_rows, changed


def split_column(headers, rows, column, sep=","):
    """Split a column in two: values after a sep go to the sibling column.

    Extra separators keep their leftovers in the original column's
    first half, so nothing is lost.
    """
    index = _require_column(headers, column)
    first = str(column).strip() + " 1"
    second = str(column).strip() + " 2"
    if first in headers or second in headers:
        raise ValueError("Split column name is already taken. Rename it first.")
    new_headers = list(headers)
    new_headers[index:index + 1] = [first, second]
    new_rows = []
    split_count = 0
    for row in rows:
        cell = _cell_at(row, index)
        parts = cell.split(sep, 1) if cell else [cell]
        left = parts[0].strip()
        right = parts[1].strip() if len(parts) > 1 else ""
        split_count += 1
        new_rows.append(
            row[:index] + [left, right] + row[index + 1:]
        )
    return new_headers, new_rows, split_count


def merge_columns(headers, rows, columns, new_name, sep=" "):
    """Merge two or more columns into one; the sources are folded away."""
    indices = [_require_column(headers, c) for c in columns]
    if len(indices) < 2:
        raise ValueError("Merging needs at least two columns.")
    if any(new_name.strip().lower() == h.strip().lower() for h in headers):
        raise ValueError(
            f"A column called {new_name!r} already exists. Pick another name."
        )
    keep = [i for i in range(len(headers)) if i not in set(indices)]
    merged_position = sum(1 for i in keep if i < min(indices))
    new_headers = [headers[i] for i in keep]
    new_headers.insert(merged_position, new_name.strip())
    new_rows = []
    for row in rows:
        pieces = [_cell_at(row, i).strip() for i in indices]
        merged = sep.join(p for p in pieces if p)
        next_row = [row[i] for i in keep]
        next_row.insert(merged_position, merged)
        new_rows.append(next_row)
    return new_headers, new_rows, len(rows)


def normalize_dates(headers, rows, columns, auto=False):
    """Normalize chosen columns to ISO dates. auto picks date-like columns."""
    if auto:
        from csvclean.profiler import guess_type
        targets = [
            h for h, i in [(headers[i], i) for i in range(len(headers))]
            if guess_type([_cell_at(r, i) for r in rows]) == "date"
        ]
    else:
        targets = list(columns)
    summary = {}
    for column in targets:
        idx = _require_column(headers, column)
        values = [_cell_at(r, idx) for r in rows]
        new_values, fixed, skipped = normalize_date_column(values)
        for r, v in zip(rows, new_values):
            if _cell_at(r, idx) != v:
                r[idx] = v
        processed = len(values) - sum(1 for v in values if not str(v).strip())
        summary[column] = {
            "processed": processed,
            "fixed": fixed,
            "skipped": skipped,
        }
    return summary


def drop_blank_rows(rows):
    blank_flags = [all(not c.strip() for c in r) for r in rows]
    kept, removed = [], 0
    for row, blank in zip(rows, blank_flags):
        if blank:
            removed += 1
        else:
            kept.append(row)
    return kept, removed


def _require_column(headers, name):
    lookup = {h.strip().lower(): i for i, h in enumerate(headers)}
    idx = lookup.get(str(name).strip().lower())
    if idx is None:
        raise ValueError(
            "Can't find a column called "
            f"{name!r}. Columns right now: {', '.join(headers)}"
        )
    return idx


def pad_rows(rows, width):
    """Give every row exactly `width` cells so writes stay tidy."""
    padded = []
    for row in rows:
        if len(row) < width:
            padded.append(list(row) + [""] * (width - len(row)))
        else:
            padded.append(list(row))
    return padded
