"""Near-duplicate detection that keeps the first row of each match group.

A row counts as a near-duplicate when, after normalization, it is very
similar to an earlier row (default similarity 0.92). We compare against
earlier rows only and skip pairs whose lengths differ a lot, which keeps
this fast enough for everyday-sized files.
"""

import difflib


def normalize_row(row):
    """Join a row into one comparable string: lowercase, no commas or
    periods, and any run of whitespace collapsed to a single space."""
    joined = " ".join(cell.strip() for cell in row if cell)
    lowered = " ".join(part.lower() for part in joined.split(" "))
    flattened = " ".join(lowered.split())
    return flattened.replace(",", "").replace(".", "")


def find_near_duplicates(rows, threshold=0.92):
    """Return a list of (row_number, similar_to_row_number, score).

    Row numbers are 1-based data rows (row 1 is the first data row),
    matching how people count rows in a spreadsheet, not the header.
    Completely blank rows are ignored entirely.
    """
    results = []
    seen = []
    for i, row in enumerate(rows):
        key = normalize_row(row)
        if key.strip() == "":
            continue
        matched = None
        for j, other in enumerate(seen):
            # Quick length filter so tiny rows don't get compared to long ones.
            if abs(len(key) - len(other)) > 0.4 * max(len(key), len(other), 1):
                continue
            score = difflib.SequenceMatcher(None, key, other).ratio()
            if score >= threshold and (matched is None or score > matched[1]):
                matched = (j + 1, score)
        if matched is not None:
            results.append((i + 1, matched[0], round(matched[1], 3)))
        else:
            seen.append(key)
    return results


def drop_near_duplicates(rows, threshold=0.92):
    """Remove rows reported as near-duplicates, keeping firsts. Returns (kept, removed)."""
    flags = {idx - 1 for idx, _, _ in find_near_duplicates(rows, threshold)}
    kept = [row for i, row in enumerate(rows) if i not in flags]
    removed = [row for i, row in enumerate(rows) if i in flags]
    return kept, removed
