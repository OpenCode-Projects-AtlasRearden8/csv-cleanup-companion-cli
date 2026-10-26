"""csvclean: a friendly CLI that cleans ugly CSVs, safely.

See README.md for the plain-English walkthrough.
"""

import argparse
import json
import sys
import urllib.error
from pathlib import Path

from csvclean import __version__
from csvclean.cleaner import (
    CASE_MODES,
    apply_case,
    drop_blank_rows,
    merge_columns,
    normalize_dates,
    pad_rows,
    rename_with_mapping,
    split_column,
    trim_headers_and_cells,
)
from csvclean.csvio import clean_output_path, load_rows, safe_output_path, write_csv
from csvclean.duplicates import drop_near_duplicates, find_near_duplicates
from csvclean.profiler import format_profile, profile_columns
from csvclean import suggestions as _suggestions
from csvclean.suggestions import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
)

FRIENDLY = "  ->"


def _fail(message):
    print(f"Sorry, that did not work.\n{message}", file=sys.stderr)
    sys.exit(2)


def cmd_profile(args):
    path = Path(args.file)
    try:
        headers, rows, encoding = load_rows(path)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _fail(f"Could not read '{path}': {exc}")
        return
    columns, shape = profile_columns(headers, rows)
    print(format_profile(columns, shape, len(rows)))
    if encoding not in ("utf-8", "utf-8-sig"):
        print(f"Note: decoded this file as {encoding} UTF-8 was not detected.")
    return 0


def cmd_clean(args):
    path = Path(args.file)
    if args.rename and not Path(args.rename).is_file():
        _fail(f"The mapping file '{args.rename}' does not exist.")
        return
    try:
        headers, rows, encoding = load_rows(path)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _fail(f"Could not read '{path}': {exc}")
        return
    actions = []
    # Pad ragged rows to header width up front - shorter rows simply get
    # blank filler cells, which makes every later step predictable.
    rows = pad_rows(rows, len(headers))
    if not args.no_trim:
        headers, rows, changed = trim_headers_and_cells(headers, rows)
        if changed:
            actions.append(f"trimmed stray whitespace in {changed} cells")
    mapping_path = Path(args.rename) if args.rename else None
    if args.rename and mapping_path.suffix.lower() == ".json":
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _fail(f"Mapping file '{mapping_path}' is not valid JSON: {exc}")
            return
        headers, missed = rename_with_mapping(headers, mapping)
        if missed:
            print(
                f"{FRIENDLY} Not every mapping name matched a column: "
                f"{', '.join(missed)}",
                file=sys.stderr,
            )
        actions.append(f"renamed columns via {mapping_path.name}")
    elif args.rename:
        try:
            old_headers, old_rows, _ = load_rows(mapping_path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            _fail(f"Could not read mapping file '{mapping_path}': {exc}")
            return
        if len(old_headers) < 2:
            _fail(
                "Mapping CSV needs two columns: old name and new name."
            )
            return
        mapping = {}
        for row in old_rows:
            old = row[0].strip()
            new = row[1].strip() if len(row) > 1 else ""
            if old and new:
                mapping[old] = new
        headers, missed = rename_with_mapping(headers, mapping)
        if missed:
            print(
                f"{FRIENDLY} Not every mapping name matched a column: "
                f"{', '.join(missed)}",
                file=sys.stderr,
            )
        actions.append(f"renamed columns via {mapping_path.name}")
    if args.case:
        try:
            instructions = parse_case_spec(args.case)
            rows, ncol, nrow = apply_case(headers, rows, instructions)
        except ValueError as exc:
            _fail(str(exc))
            return
        modes = " and ".join(sorted({m for m, _ in instructions}))
        actions.append(
            f"applied {modes} case to {ncol} column(s) x {nrow} rows"
        )
    if args.split:
        try:
            headers, rows, count = split_column(
                headers, rows, args.split, sep=args.split_sep
            )
        except ValueError as exc:
            _fail(str(exc))
            return
        actions.append(
            f"split column '{args.split}' into two columns ({count} values)"
        )
    if args.merge:
        if not args.merge_name:
            _fail("Merging needs a destination: add --merge-name \"Merged Name\".")
            return
        try:
            headers, rows, count = merge_columns(
                headers, rows, args.merge, args.merge_name, sep=args.merge_sep
            )
        except ValueError as exc:
            _fail(str(exc))
            return
        actions.append(
            f"merged {', '.join(args.merge)} into '{args.merge_name}' ({count} rows)"
        )
    if args.dates:
        try:
            summary = normalize_dates(
                headers,
                rows,
                [c.strip() for c in args.dates.split(",") if c.strip()]
                if args.dates != "auto"
                else [],
                auto=args.dates == "auto",
            )
            for column, info in summary.items():
                detail = f"normalized {info['processed']} date(s) in '{column}'"
                if info["fixed"] != info["processed"] and info["processed"]:
                    detail += f" ({info['fixed']} rewritten)"
                if info["skipped"]:
                    detail += f"; left {len(info['skipped'])} unrecognizable alone"
                print(f"{FRIENDLY} Dates: {detail}")
        except ValueError as exc:
            _fail(str(exc))
            return
    removed_blanks = 0
    if not args.no_drop_blank:
        rows, removed_blanks = drop_blank_rows(rows)
        if removed_blanks:
            actions.append(f"dropped {removed_blanks} completely blank row(s)")
    if not args.no_dupes_report and not args.drop_near_dupes:
        dupes = find_near_duplicates(rows)
        if dupes:
            print(
                f"{FRIENDLY} Near-duplicate check: found {len(dupes)} "
                f"near-duplicate row(s) (default similarity 0.92)."
            )
            for row_no, similar_to, score in dupes[:10]:
                print(
                    f"      row {row_no} looks {score:.2f}-similar to row {similar_to}"
                )
            if len(dupes) > 10:
                print(f"      ...and {len(dupes) - 10} more")
            print(
                f"      Kept them all. To drop near-duplicates, rerun with "
                f"--drop-near-dupes."
            )
        else:
            print(f"{FRIENDLY} Near-duplicate check: clean.")
    if args.drop_near_dupes:
        rows, removed_dupes = drop_near_duplicates(rows)
        actions.append(f"dropped {len(removed_dupes)} near-duplicate row(s)")
    out_dir = Path(args.out_dir) if args.out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = (
        safe_output_path(Path(args.out)) if args.out else clean_output_path(path, out_dir)
    )
    headers, rows = pad_for_write(headers, rows)
    write_csv(out_path, headers, rows)
    total = len(rows)
    print(f"{FRIENDLY} Wrote {out_path} (did not overwrite anything).")
    for action in actions:
        print(f"{FRIENDLY} {action}")
    if args.check_rows is not None:
        expected = args.check_rows
        if total == expected:
            print(f"{FRIENDLY} Row check OK: {total} rows matched the expected {expected}.")
        else:
            print(
                f"{FRIENDLY} Row check MISMATCH: got {total} rows, expected {expected}.",
                file=sys.stderr,
            )
            if args.strict:
                sys.exit(3)
    print(f"{FRIENDLY} Final row count: {total} data rows, {len(headers)} columns.")
    return 0


def pad_for_write(headers, rows):
    """Pad rows to header width so the cleaned file stays rectangular."""
    return headers, pad_rows(rows, len(headers))


def parse_case_spec(spec):
    """Accept 'lower', 'upper', 'title', or per-column 'col=lower,col2=title'.

    Returns instructions of (mode, column_or_None) for the cleaner.
    """
    if "=" not in spec:
        if spec not in CASE_MODES:
            raise ValueError(
                f"--case understands {', '.join(CASE_MODES)}, or col=mode pairs."
            )
        return [(spec, None)]
    instructions = []
    for pair in spec.split(","):
        if "=" not in pair:
            raise ValueError(
                f"'{pair}' in --case is not like col=mode. Example: name=lower"
            )
        col, m = pair.split("=", 1)
        mode_candidate = m.strip()
        if mode_candidate not in CASE_MODES:
            raise ValueError(
                f"'{mode_candidate}' is not one of {', '.join(CASE_MODES)} "
                f"(column {col.strip()!r})."
            )
        instructions.append((mode_candidate, col.strip() or None))
    return instructions


def cmd_suggest(args):
    path = Path(args.file)
    try:
        headers, rows, _ = load_rows(path)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _fail(f"Could not read '{path}': {exc}")
        return
    samples = _suggestions.collect_samples(headers, rows)
    print("Rule-based suggestions (no server needed):")
    for original, new in _suggestions.local_suggestions(headers).items():
        print(f"  - {original!r} -> {new!r}")
    if not _suggestions.local_suggestions(headers):
        print("  (none needed - the headers already look tidy)")
    print()
    print(f"Ask {args.model} at {args.base_url} for a second opinion...")
    prompt = _suggestions.build_prompt(headers, samples)
    try:
        llm = _suggestions.request_llm_suggestions(
            args.base_url, args.model, prompt, args.timeout
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError) as exc:
        print(f"...no answer ({exc}).")
        print("No problem. The rule-based suggestions above stay in your shell history.")
        return 0
    if not llm:
        print("...it answered, but nothing usable came back.")
        return 0
    print("AI-suggested mapping (paste into a JSON file for --rename):")
    print(json.dumps(llm, indent=2, ensure_ascii=False))
    if args.save:
        out = safe_output_path(Path(args.save))
        out.write_text(json.dumps(llm, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Saved AI mapping to {out}.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="csvclean",
        description=(
            "A friendly, local-first CLI that cleans ugly CSVs for people "
            "who would rather not open a spreadsheet. It profiles columns, "
            "trims, fixes case, renames via a mapping file, splits and merges "
            "columns, normalizes dates, checks for near-duplicates and row "
            "counts, and always writes a brand-new *-cleaned.csv file. "
            "No overwrites. No deletions. No secrets."
        ),
    )
    parser.add_argument("--version", action="version", version=f"csvclean {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_profile = sub.add_parser("profile", help="Look before you clean")
    p_profile.add_argument("file", help="The CSV you want to understand")
    p_profile.set_defaults(func=cmd_profile)

    p_clean = sub.add_parser("clean", help="Clean a CSV into *-cleaned.csv")
    p_clean.add_argument("file", help="The CSV to clean")
    p_clean.add_argument(
        "--rename",
        help="Path to a .json mapping file: {'old column': 'new column', ...}",
    )
    p_clean.add_argument(
        "--no-trim", action="store_true", help="Leave whitespace exactly as found"
    )
    p_clean.add_argument(
        "--case",
        help="lower, upper, title, or pairs like name=lower,city=title",
    )
    p_clean.add_argument("--split", help="Column name to split in two")
    p_clean.add_argument(
        "--split-sep", default=",", help="Separator to split on (default ,)"
    )
    p_clean.add_argument(
        "--merge", nargs="+", metavar="COL", help="Columns to merge into one"
    )
    p_clean.add_argument("--merge-name", help="Name for the merged column")
    p_clean.add_argument("--merge-sep", default=" ", help="Separator for merging")
    p_clean.add_argument(
        "--dates",
        help="Comma-separated columns to normalize, or 'auto'",
    )
    p_clean.add_argument(
        "--no-dupes-report", action="store_true", help="Skip near-duplicate check"
    )
    p_clean.add_argument(
        "--drop-near-dupes", action="store_true", help="Remove near-duplicate rows"
    )
    p_clean.add_argument(
        "--no-drop-blank", action="store_true", help="Keep completely blank rows"
    )
    p_clean.add_argument(
        "--out", help="Write to a specific path instead of FILE-cleaned.csv"
    )
    p_clean.add_argument("--out-dir", help="Directory for the cleaned file")
    p_clean.add_argument(
        "--check-rows", type=int, help="Expected number of data rows after cleaning"
    )
    p_clean.add_argument(
        "--strict", action="store_true", help="Exit with an error if row check fails"
    )
    p_clean.set_defaults(func=cmd_clean)

    p_suggest = sub.add_parser(
        "suggest", help="Optional AI help for messy column names"
    )
    p_suggest.add_argument("file", help="CSV whose column names could breathe more")
    p_suggest.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="OpenAI-compatible base URL (default: local Ollama)",
    )
    p_suggest.add_argument(
        "--model", default=DEFAULT_MODEL, help="Model name at the endpoint"
    )
    p_suggest.add_argument("--timeout", type=float, default=20, help="Seconds to wait")
    p_suggest.add_argument("--save", help="Save the AI's mapping to this .json path")
    p_suggest.set_defaults(func=cmd_suggest)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Stopped - nothing was written or deleted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
