"""Column profiling: look before you clean."""

from csvclean.dates import try_parse_date

SAMPLE_LIMIT = 5


def _looks_numeric(values):
    filled = [v for v in values if v]
    if not filled:
        return False
    hits = 0
    for v in filled:
        try:
            float(v.replace(",", ""))
        except ValueError:
            hits += 1
    return hits <= max(1, len(filled) // 20)  # tiny slack for one typo/stragglers


def guess_type(values):
    filled = [v.strip() for v in values if v and v.strip()]
    if not filled:
        return "empty"
    date_hits = sum(1 for v in filled if try_parse_date(v) is not None)
    if date_hits / len(filled) >= 0.8:
        return "date"
    if _looks_numeric(filled):
        return "number"
    return "text"


def profile_columns(headers, rows):
    """Profile every column. Returns a list of dicts, one per header column."""
    width = len(headers)
    short_rows = sum(1 for r in rows if len(r) < width)
    long_rows = sum(1 for r in rows if len(r) > width)
    columns = []
    for i, header in enumerate(headers):
        values = []
        empty = 0
        for row in rows:
            cell = row[i] if i < len(row) else ""
            if cell is None or (isinstance(cell, str) and cell.strip() == ""):
                empty += 1
            else:
                values.append(cell)
        needs_trim = any(
            v != v.strip() for v in values
        )
        unique_samples = []
        for v in values:
            if v not in unique_samples:
                unique_samples.append(v)
            if len(unique_samples) >= SAMPLE_LIMIT:
                break
        columns.append(
            {
                "name": header,
                "filled": len(values),
                "empty": empty,
                "samples": unique_samples,
                "type": guess_type(values),
                "needs_trim": needs_trim or header != header.strip(),
            }
        )
    shape = {"short_rows": short_rows, "long_rows": long_rows}
    return columns, shape


def format_profile(columns, shape, total_rows):
    """Turn a profile into friendly paragraphs of plain English."""
    lines = []
    lines.append(f"Profile of {len(columns)} columns across {total_rows} data rows")
    lines.append("")
    if shape["short_rows"] or shape["long_rows"]:
        if shape["short_rows"]:
            lines.append(
                f"Note: {shape['short_rows']} row(s) have fewer cells than the header row."
            )
        if shape["long_rows"]:
            lines.append(
                f"Note: {shape['long_rows']} row(s) have extra cells beyond the header row."
            )
        lines.append("")
    for col in columns:
        pct = (100.0 * col["filled"] / total_rows) if total_rows else 0.0
        line = f"  - {col['name']}: {col['type']}, {col['filled']}/{total_rows} filled ({pct:.0f}%)"
        flags = []
        if col["empty"]:
            flags.append(f"{col['empty']} empty")
        if col["needs_trim"]:
            flags.append("stray whitespace")
        if flags:
            line += " [" + ", ".join(flags) + "]"
        lines.append(line)
        if col["samples"]:
            shown = ", ".join(repr(s) for s in col["samples"][:3])
            lines.append(f"      samples: {shown}")
    lines.append("Looks like a good next step? Run: csvclean clean <file>")
    lines.append("")
    return "\n".join(lines)
