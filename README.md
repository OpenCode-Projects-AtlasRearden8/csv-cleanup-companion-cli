# csvclean-companion

A friendly, local-first command-line tool that cleans ugly CSV files for
people who would rather never open a spreadsheet. It looks at your columns
first, fixes the common messes, and always writes a **brand-new** file —
your original is never touched, overwritten, or deleted.

Built by **Asdale Dynamics, LLC** — plain English, step by step, never
condescending. Learn more at <https://dylanasdale.github.io>.

## What it does

- **Profile** every column: what it contains, how empty it is, whether it
  looks like dates or numbers, and whether stray whitespace is sneaking in.
- **Trim and case fixes**: strips pesky leading/trailing spaces from cells
  and headers; changes case per column (`lower`, `upper`, `title`).
- **Rename columns** from a mapping file (JSON or a simple two-column CSV).
- **Split and merge columns** (think "Full Name" → "First" + "Last", or
  scattering a name across three columns back into one).
- **Friendly date normalization** to clean ISO dates like `2025-06-01`.
- **Near-duplicate detection**, reported clearly, with an explicit opt-in
  flag (`--drop-near-dupes`) if you want them removed.
- **Row-count sanity checks**: tells you if the row count grew, shrank, or
  matched what you expected.
- **Always a new file**: output is `yourfile-cleaned.csv`. If that name is
  taken, it moves to `yourfile-cleaned-2.csv` and so on. No overwrites,
  no deletes. Ever.
- **Optional AI suggestions** for column names through any
  OpenAI-compatible endpoint — with local-first defaults and **no API keys,
  ever** (more below).

## Quick start

You need Python 3.9 or newer. No third-party packages required.

```bash
# look before you clean
python3 -m csvclean profile messy.csv

# clean it (writes messy-cleaned.csv)
python3 -m csvclean clean messy.csv
```

If you install the package (`pip install .` where allowed), you can also
use the short `csvclean` command instead of `python3 -m csvclean`.

## Cleaning, step by step

You pick only the fixes you want. Every switch is optional.

```bash
python3 -m csvclean clean messy.csv \
    --rename mapping.json \
    --case "customer_name=title,email_address=lower" \
    --dates "Join Date,Leave Date" \
    --check-rows 120
```

- `--trim` is on by default. Add `--no-trim` to leave whitespace exactly
  as found.
- `--case` accepts `lower`, `upper`, `title` (applied to every column), or
  pairs like `customer_name=title,email_address=lower`.
- The order is: trim → rename → everything else. Mapping files use the
  **original** column names (whitespace around names is ignored); all
  other column references use the names **after** renaming.

### Renaming with a mapping file

`mapping.json` (any names you did not list are left unchanged):

```json
{
  "Customer Name": "customer_name",
  "Email": "email_address"
}
```

Or `mapping.csv`, a simple two-column table:

```csv
old_name,new_name
Customer Name,customer_name
Email,email_address
```

### Splitting and merging

```bash
# Full Name -> "Full Name 1" + "Full Name 2" (splitting on a space)
python3 -m csvclean clean people.csv --split "Full Name" --split-sep " "

# fold City + Street into one new column named Locale
python3 -m csvclean clean people.csv --merge City Street --merge-name Locale \
    --merge-sep " - "
```

### Dates, duplicates, and row checks

```bash
# normalize one or more columns to ISO dates
python3 -m csvclean clean messy.csv --dates "Join Date"
# ...or let the profiler find the date-like columns for you
python3 -m csvclean clean messy.csv --dates auto

# report near-duplicates (kept, just flagged)
python3 -m csvclean clean messy.csv
# remove them, keeping the first of each match group
python3 -m csvclean clean messy.csv --drop-near-dupes

# sanity-check the row count; --strict turns a mismatch into an error
python3 -m csvclean clean messy.csv --check-rows 120
```

A note on ambiguous dates: `03/04/2025` reads as US order (March 4) unless
the first number is 13 or more, in which case it is clearly a day
(`31/01/2025` → `2025-01-31`). Values the tool cannot recognize as dates
are left exactly as-is and counted in the summary.

## Optional AI column-name suggestions (never a key)

```bash
python3 -m csvclean suggest messy.csv
```

You always get honest, rule-based suggestions (`Order ID` → `order_id`)
with no server involved. If you additionally run a local AI, the tool will
ask it for a second opinion:

- Default endpoint: Ollama at `http://localhost:11434/v1`
  (default model: `llama3.2`).
- Point it at **any OpenAI-compatible base URL**:
  `--base-url http://localhost:8000/v1 --model my-model`.
- Our promise: this tool has no API-key handling at all. It never asks for
  one, never stores one, and never sends one. It calls only
  `<base-url>/chat/completions` on the base URL you give it.

If the reply is a JSON object, it is printed ready-to-save, so you can use
it as a rename mapping file (`--save mapping.json` in suggest, then
`--rename mapping.json` in clean).

## Running the tests

```bash
python3 -m pytest tests
```

The suite uses small fixture CSVs in `tests/fixtures/` — messy real-world
shapes, friendly dates, duplicates, and row-count cases. Python 3.9+,
standard library only.

## Design promises

1. **Never overwrite, never delete.** Every write goes to a new file.
2. **Local-first.** No cloud calls unless you ask for one explicitly with
   `csvclean suggest`, and even then only to a server you name.
3. **No secrets and no personal data** handling beyond the file you point
   it at. Nothing is logged or shipped anywhere by this tool.
4. **Plain English, step by step, never condescending.**

## License

MIT — see `LICENSE`. © **Asdale Dynamics, LLC**.
