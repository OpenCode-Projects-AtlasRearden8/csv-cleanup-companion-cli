"""Reading and writing CSVs, with forgiving decoding and safe filenames."""

import csv
import io


def load_text(path):
    """Return the file's text, trying the encodings ugly CSVs actually use."""
    data = path.read_bytes()
    errors = []
    # utf-8-sig also quietly removes the Excel-favorite BOM if present.
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    # latin-1 can't fail, so this line is a safety net, not a real path.
    raise UnicodeDecodeError("unknown", data, 0, 1, "; ".join(errors))


def load_rows(path):
    """Read a CSV into (headers, rows).

    headers is list[str]; rows is a list of list[str]. Rows are kept
    exactly as found - short or ragged rows are allowed and reported
    upstream rather than silently mangled.
    """
    text, encoding = load_text(path)
    reader = csv.reader(io.StringIO(text))
    records = list(reader)
    if not records:
        raise ValueError(
            f"'{path.name}' looks completely empty. "
            "There is nothing to clean here."
        )
    headers = records[0]
    rows = records[1:]
    return headers, rows, encoding


def quote_needing_cell(value):
    """True if a value would be nicer with surrounding quotes when written."""
    return any(c in value for c in ',"\n\r')


def write_csv(path, headers, rows):
    """Write headers + rows as CSV text, always creating a new file."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


def clean_output_path(input_path, out_dir, suffix="-cleaned"):
    """Return a path that never overwrites an existing file.

    Example: report.csv -> report-cleaned.csv. If that exists, we move
    on to report-cleaned-2.csv, report-cleaned-3.csv, and so on.
    """
    stem = input_path.stem + suffix
    candidate = out_dir / f"{stem}{input_path.suffix or '.csv'}"
    n = 2
    while candidate.exists():
        candidate = out_dir / f"{stem}-{n}{input_path.suffix or '.csv'}"
        n += 1
    return candidate


def safe_output_path(requested_path):
    """Return a non-existing path for an explicitly requested output file.

    Never overwrites. If 'mapping-cleaned.csv' exists, tries
    'mapping-cleaned-2.csv', and so on.
    """
    candidate = requested_path
    n = 2
    while candidate.exists():
        stem = requested_path.stem
        candidate = requested_path.with_name(f"{stem}-{n}{requested_path.suffix}")
        n += 1
    return candidate
