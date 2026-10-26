# STATUS.md — csvclean-companion

Built 2026-10-26 by **Asdale Dynamics, LLC** (CSV cleanup companion CLI for
spreadsheet-shy users — plain English, step by step, never condescending).

## What was built

`csvclean`, a zero-dependency (Python 3.9+ standard library only) CLI that
cleans ugly CSVs and **always writes a new `*-cleaned.csv` file** — it never
overwrites and never deletes anything (existing outputs shift to
`*-cleaned-2.csv`, `-3.csv`, …).

Features, as requested:

- **Profile columns** — `profile` shows each column's fill rate, inferred
  type (date/number/text/empty), sample values, stray-whitespace flags, and
  warns about rows that have fewer or extra cells than the header.
- **Trim + case fixes** — trim is on by default (`--no-trim` to opt out);
  `--case lower|upper|title` or per-column pairs like
  `customer_name=title,email_address=lower`.
- **Rename via mapping file** — `--rename mapping.json` (or a two-column
  `mapping.csv`). Keys match whitespace-tolerantly; unmatched keys are
  reported, never fatal.
- **Split/merge columns** — `--split COL [--split-sep SEP]` creates
  `COL 1`/`COL 2`; `--merge COL COL [--merge-name NAME] [--merge-sep SEP]`.
- **Friendly date normalization** — `--dates "Col1,Col2"` or `--dates auto`;
  outputs ISO `YYYY-MM-DD`; unrecognizable values are left untouched and
  counted. Ambiguous numeric dates default to US order unless the first
  number is clearly a day.
- **Near-duplicate detection** — similarity vs earlier rows (default 0.92),
  reported with row numbers and scores; removal only with the explicit
  `--drop-near-dupes` flag. Completely blank rows are dropped by default
  (`--no-drop-blank` keeps them).
- **Row-count sanity checks** — `--check-rows N` prints OK/MISMATCH against
  the final row count; `--strict` makes a mismatch exit with code 3.
- **Optional AI column-mapping suggestions** — `suggest` always gives honest
  rule-based snake_case hints with no server, then asks a configurable
  OpenAI-compatible `/chat/completions` endpoint for a second opinion.
  Default base URL is local Ollama `http://localhost:11434/v1`
  (model `llama3.2`); any base URL works via `--base-url`. The tool has **no
  API-key handling at all** — it never asks for, stores, or sends a key.

Layout: `csvclean/` (cli, csvio, profiler, cleaner, dates, duplicates,
suggestions), `tests/` (fixtures + suite), `README.md`, `LICENSE`
(MIT — exactly `Copyright (c) 2026 Asdale Dynamics, LLC`), `pyproject.toml`.

## How to run it

```bash
python3 -m csvclean profile FILE.csv
python3 -m csvclean clean FILE.csv [options]     # writes FILE-cleaned.csv
python3 -m csvclean suggest FILE.csv [--base-url URL --model NAME]
```

Options for `clean`: `--rename mapping.json|mapping.csv`, `--no-trim`,
`--case ...`, `--split/--split-sep`, `--merge ... --merge-name`,
`--merge-sep`, `--dates`, `--drop-near-dupes`, `--no-dupes-report`,
`--no-drop-blank`, `--out`, `--out-dir`, `--check-rows N`, `--strict`.
Colours, jargon, and data exfiltration: none.

## How it was verified

- `python3 -m pytest tests` — **40/40 passed** (fixture CSVs in
  `tests/fixtures/`: messy ragged/whitespace/date/duplicate file, dates,
  duplicates, people split+merge, row counts, good/bad mapping files).
- CLI smoke runs performed directly:
  - `profile` on a ragged 7-row file: fill rates + "fewer cells than the
    header" note + whitespace flags — correct.
  - `clean` with `--rename` (JSON) + `--case` + `--dates "Join Date"` +
    `--check-rows`: renamed headers, ISO dates, title-cased names, blank
    row dropped, MISMATCH warning reported, original file byte-identical.
  - `clean` twice into the same folder + `--out-dir` + `--out`: produced
    `-cleaned.csv`, `-cleaned-2.csv` without touching the first output.
  - `--drop-near-dupes`: 2 near-duplicates found (report run) then dropped
    (explicit flag run); `--check-rows` reflected the drop.
  - `suggest` against a closed port: friendly "no answer" fallback, exit 0,
    rule-based suggestions still delivered (no `Connection refused` crash).
  - A fake OpenAI-compatible endpoint (unit-mocked) shows the exact request
    shape: `POST <base-url>/chat/completions`, `model` + `messages`,
    **no key fields anywhere**.
  - `python3 -m csvclean --version` → `csvclean 0.1.0`.
- Packaging: `pip install . --dry-run` metadata build succeeds and
  resolves `csvclean-companion-0.1.0` with the `csvclean` console script.
- Bug fixes found by the verification loop (all now covered by tests):
  duplicated near-dupe report rows from an inner-loop append, a ragged-row
  `IndexError` in case fixes, empty date cells counted as "skipped", tuple
  indexing in the similarity matcher.

## Known gaps (honest list)

- Near-duplicate detection compares each row to earlier kept rows — it is
  quadratic, tuned for everyday file sizes (thousands of rows), not
  millions. Large files warn by complexity, not by spinning your fans.
- Ambiguous numeric dates default to US month/day order; there is no
  per-locale option yet.
- Values with date *and* time (e.g. `2025-01-05 10:30`) are left untouched
  rather than mangled; date-only output only.
- `suggest` does not validate model availability beyond a clean error; base
  URL/model are CLI flags (no env-var override yet).
- CSV dialect sniffing (semicolon/tab delimiters) and header-comment skips
  are not supported yet.
- Rule-based suggestions only snake_case existing names; they cannot invent
  semantic names — that is what the optional AI pass is for.
- Encodings: UTF-8 (with BOM), cp1252, latin-1 fallback; other rare encodings
  may need a manual pre-pass.

Legal: MIT License — `LICENSE` reads exactly `Copyright (c) 2026 Asdale
Dynamics, LLC` on its copyright line; the README credits Asdale Dynamics,
LLC. No secrets, API keys, or personal data are committed in this repo.
