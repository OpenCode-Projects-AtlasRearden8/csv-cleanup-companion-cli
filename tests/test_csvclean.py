import json
import shutil
import sys
from pathlib import Path

import pytest

from csvclean import cli
from csvclean import suggestions as sugg
from csvclean.cli import parse_case_spec
from csvclean.csvio import clean_output_path, safe_output_path
from csvclean.dates import to_iso
from csvclean.duplicates import (
    drop_near_duplicates,
    find_near_duplicates,
    normalize_row,
)

FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv):
    code = cli.main(list(argv))
    return code


def read(path):
    return Path(path).read_text(encoding="utf-8")


def use_fixture(tmp_path, name):
    """Copy a fixture into the test's own sandbox so we can safely mutate."""
    target = tmp_path / name
    shutil.copy(FIXTURES / name, target)
    return target


# ---------- profiling ----------


def test_profile_describes_columns(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    code = run_cli("profile", str(csv_file))
    out = capsys.readouterr().out
    assert code == 0
    assert "7 data rows" in out
    assert "Customer Name" in out
    assert "stray whitespace" in out
    assert "fewer cells than the header" in out


def test_profile_missing_file_exits_friendly(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli("profile", str(tmp_path / "nope.csv"))
    out = capsys.readouterr()
    assert exc.value.code == 2
    assert "did not work" in out.err


# ---------- *.csv basics: trim, case, safe output ----------


def test_clean_trims_and_writes_new_file(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    code = run_cli("clean", str(csv_file))
    out = capsys.readouterr().out
    assert code == 0
    assert "trimmed stray whitespace" in out
    cleaned = tmp_path / "messy-cleaned.csv"
    assert cleaned.exists()
    assert "  , Dana Whitfield ," not in read(cleaned)
    assert "Dana Whitfield" in read(cleaned)
    # The original stays untouched, byte for byte.
    assert read(csv_file) == read(FIXTURES / "messy.csv")


def test_clean_never_overwrites(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    sentinel = tmp_path / "messy-cleaned.csv"
    sentinel.write_text("HANDS OFF", encoding="utf-8")
    code = run_cli("clean", str(csv_file))
    out = capsys.readouterr().out
    assert code == 0
    assert read(sentinel) == "HANDS OFF"
    assert (tmp_path / "messy-cleaned-2.csv").exists()
    assert "did not overwrite anything" in out


def test_out_dir_and_custom_out(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    dest = tmp_path / "results"
    code = run_cli("clean", str(csv_file), "--out-dir", str(dest))
    assert code == 0
    assert (dest / "messy-cleaned.csv").exists()
    custom = tmp_path / "custom.csv"
    custom.write_text("keep", encoding="utf-8")
    code = run_cli("clean", str(csv_file), "--out", str(custom))
    assert code == 0
    assert read(custom) == "keep"
    assert (tmp_path / "custom-2.csv").exists()


def test_safe_output_path_increments(tmp_path):
    first = safe_output_path(tmp_path / "report-cleaned.csv")
    first.write_text("x", encoding="utf-8")
    second = safe_output_path(tmp_path / "report-cleaned.csv")
    second.write_text("x", encoding="utf-8")
    third = clean_output_path(tmp_path / "report.csv", tmp_path)
    assert first.name == "report-cleaned.csv"
    assert second.name == "report-cleaned-2.csv"
    assert third.name == "report-cleaned-3.csv"
    assert read(first) == read(second) == "x"


# ---------- renaming via mapping file ----------


def test_rename_with_json_mapping(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    mapping = use_fixture(tmp_path, "mapping.json")
    code = run_cli("clean", str(csv_file), "--rename", str(mapping))
    out = capsys.readouterr().out
    assert code == 0
    cleaned = read(tmp_path / "messy-cleaned.csv")
    assert "customer_name,email_address" in cleaned.lower()
    assert "Customer Name" not in cleaned


def test_rename_with_csv_mapping(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    mapping = use_fixture(tmp_path, "mapping.csv")
    code = run_cli("clean", str(csv_file), "--rename", str(mapping))
    assert code == 0
    cleaned = read(tmp_path / "messy-cleaned.csv").lower()
    assert "customer_name,email_address" in cleaned


def test_rename_reports_unmatched_keys(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    mapping = use_fixture(tmp_path, "bad-mapping.json")
    run_cli("clean", str(csv_file), "--rename", str(mapping))
    err = capsys.readouterr().err
    assert "Does Not Exist" in err
    # A null value is skipped like an honest miss instead of crashing.
    assert "Order ID" in err


def test_rename_missing_file_is_friendly(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    with pytest.raises(SystemExit) as exc:
        run_cli("clean", str(csv_file), "--rename", str(tmp_path / "gone.json"))
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert "does not exist" in err


# ---------- case fixes ----------


def test_case_pairs_apply_to_chosen_columns(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    code = run_cli("clean", str(csv_file), "--case", "Customer Name=lower,City=title")
    out = capsys.readouterr().out
    assert code == 0
    assert "lower" in out
    cleaned = read(tmp_path / "messy-cleaned.csv")
    assert "dana whitfield" in cleaned


def test_case_rejects_bad_mode(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    with pytest.raises(SystemExit) as exc:
        run_cli("clean", str(csv_file), "--case", "shout")
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert "--case understands" in err


def test_parse_case_spec_happy_paths():
    assert parse_case_spec("lower") == [("lower", None)]
    assert parse_case_spec("a=upper,b=upper") == [
        ("upper", "a"),
        ("upper", "b"),
    ]
    assert parse_case_spec("a=lower,b=title") == [
        ("lower", "a"),
        ("title", "b"),
    ]
    with pytest.raises(ValueError):
        parse_case_spec("shout")
    with pytest.raises(ValueError):
        parse_case_spec("a=shout")


def test_case_missing_column_is_friendly(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    with pytest.raises(SystemExit) as exc:
        run_cli("clean", str(csv_file), "--case", "Not There=lower")
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert "Can't find a column" in err


# ---------- split and merge ----------


def test_split_column(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "people.csv")
    code = run_cli("clean", str(csv_file), "--split", "Full Name", "--split-sep", " ")
    out = capsys.readouterr().out
    assert code == 0
    assert "split column 'Full Name'" in out
    cleaned = read(tmp_path / "people-cleaned.csv")
    assert "Full Name 1,Full Name 2" in cleaned
    assert "Dana,Whitfield" in cleaned
    assert "Natarajan" in cleaned


def test_merge_columns(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "people.csv")
    code = run_cli(
        "clean",
        str(csv_file),
        "--merge",
        "City",
        "Street",
        "--merge-name",
        "Locale",
        "--merge-sep",
        " - ",
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "merged City, Street into 'Locale'" in out
    cleaned = read(tmp_path / "people-cleaned.csv")
    assert "Locale" in cleaned
    assert "Springfield - 12 Oak St" in cleaned
    assert "Email" in cleaned  # untouched columns survive
    assert "City" not in cleaned.split("\n")[0]  # source folded away


def test_merge_requires_destination(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "people.csv")
    with pytest.raises(SystemExit) as exc:
        run_cli("clean", str(csv_file), "--merge", "City", "Street")
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert "--merge-name" in err


def test_split_missing_column_is_friendly(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "people.csv")
    with pytest.raises(SystemExit) as exc:
        run_cli("clean", str(csv_file), "--split", "Middle Name")
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert "Can't find a column" in err
    assert "Full Name" in err  # shows what exists instead


# ---------- friendly dates ----------


def test_to_iso_known_values():
    assert to_iso("2025-06-01") == "2025-06-01"
    assert to_iso("Jan 5 2025") == "2025-01-05"
    assert to_iso("03/14/2025") == "2025-03-14"
    assert to_iso("4/22/2024") == "2024-04-22"
    assert to_iso("February 3 2025") == "2025-02-03"
    assert to_iso("31/01/2025") == "2025-01-31"  # day must be first
    assert to_iso("12/31/2025") == "2025-12-31"
    assert to_iso("01/02/25") == "2025-01-02"
    assert to_iso("not a date") is None
    assert to_iso("") is None
    # 13+ in first slot can only be a day; other cases default to US order.
    assert to_iso("05/06/2025") == "2025-05-06"


def test_dates_explicit_column(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "dates.csv")
    code = run_cli("clean", str(csv_file), "--dates", "Join Date")
    out = capsys.readouterr().out
    assert code == 0
    assert "normalized 5 date(s) in 'Join Date'" in out
    cleaned = read(tmp_path / "dates-cleaned.csv")
    assert "2025-01-05" in cleaned
    assert "2025-01-02" in cleaned
    assert "01/02/25" not in cleaned


def test_dates_auto(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "dates.csv")
    code = run_cli("clean", str(csv_file), "--dates", "auto")
    out = capsys.readouterr().out
    assert code == 0
    # auto finds the Join Date column (Item/Qty columns do not exist here)
    assert "normalized 5 date(s) in 'Join Date'" in out


def test_dates_leaves_junk_alone(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    code = run_cli("clean", str(csv_file), "--dates", "Join Date")
    out = capsys.readouterr().out
    assert code == 0
    # The dollar-style dates all parse; messy value "" stays quietly empty.
    assert "unrecognizable" not in out


def test_dates_bad_column_is_friendly(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "messy.csv")
    with pytest.raises(SystemExit) as exc:
        run_cli("clean", str(csv_file), "--dates", "Born On")
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert "Can't find a column called 'Born On'" in err
    assert "Join Date" in err


# ---------- near duplicates ----------


def test_normalize_row_blanks_noise():
    assert (
        normalize_row(["  Dana ", "dana@example.com", "A-100, Inc."])
        == normalize_row(["dana", "DANA@EXAMPLE.COM", "A-100  inc."])
    )


def test_find_near_duplicates_flags_copy_and_case_variant():
    rows = [
        ["Dana", "dana@example.com", "A100"],
        ["Marcus", "marcus@example.com", "B200"],
        ["marcus", " marcus@example.com", "B200"],
        ["Priya", "priya@example.com", "C300"],
    ]
    dupes = find_near_duplicates(rows)
    assert dupes[0] == (3, 2, dupes[0][2])  # row 3 resembles row 2
    assert dupes[0][2] >= 0.92
    kept, removed = drop_near_duplicates(rows)
    assert removed == [rows[2]]  # the case-variant copy is dropped
    assert kept == [rows[0], rows[1], rows[3]]


def test_dupe_report_on_messy_file(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "dupes.csv")
    code = run_cli("clean", str(csv_file))
    out = capsys.readouterr().out
    assert code == 0
    assert "found 2 near-duplicate row(s)" in out
    assert "Kept them all" in out
    cleaned = read(tmp_path / "dupes-cleaned.csv")
    assert cleaned.count("A100") >= 2  # report only, nothing dropped


def test_drop_near_dupes(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "dupes.csv")
    code = run_cli("clean", str(csv_file), "--drop-near-dupes")
    out = capsys.readouterr().out
    assert code == 0
    assert "dropped 2 near-duplicate row(s)" in out
    cleaned = read(tmp_path / "dupes-cleaned.csv")
    assert cleaned.count("A100") == 1
    assert "Priya" in cleaned


# ---------- row-count sanity checks ----------


def test_check_rows_ok(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "rowcount.csv")
    code = run_cli("clean", str(csv_file), "--check-rows", "3")
    out = capsys.readouterr().out
    assert code == 0
    assert "matched the expected 3" in out


def test_check_rows_mismatch(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "rowcount.csv")
    code = run_cli("clean", str(csv_file), "--check-rows", "9")
    out, err = capsys.readouterr()
    assert code == 0  # warning in stderr, still writes the file
    assert "MISMATCH" in err
    assert (tmp_path / "rowcount-cleaned.csv").exists()


def test_check_rows_strict(tmp_path, capsys):
    csv_file = use_fixture(tmp_path, "rowcount.csv")
    with pytest.raises(SystemExit) as exc:
        run_cli("clean", str(csv_file), "--check-rows", "9", "--strict")
    err = capsys.readouterr().err
    assert exc.value.code == 3
    assert "MISMATCH" in err


# ---------- coding-safe suggestions (offline) ----------


def test_local_suggestions_snake_cases():
    sugg_map = sugg.local_suggestions(["Order ID", "Customer Name", "email"])
    assert sugg_map["Order ID"] == "order_id"
    assert sugg_map["Customer Name"] == "customer_name"
    assert "email" not in sugg_map  # already tidy


def test_local_suggestions_idempotent_on_tidy_headers():
    assert sugg.local_suggestions(["email", "join_date"]) == {}


def test_build_prompt_lists_columns_and_rules():
    prompt = sugg.build_prompt(
        ["Order ID", "Email"], {"Order ID": ["1"], "Email": ["a@b.c"]}
    )
    assert "Order ID" in prompt
    assert "JSON object" in prompt


def test_extract_json_mapping_ops():
    assert sugg.extract_json_mapping('Sure: {"a": "b"}') == {"a": "b"}
    assert sugg.extract_json_mapping('```json\n{"x": "y"}\n```') == {"x": "y"}
    assert sugg.extract_json_mapping("no brace at all") is None
    assert sugg.extract_json_mapping('{"n": null, "s": "v"}') == {"s": "v"}
    assert sugg.extract_json_mapping("[1, 2]") is None


# ---------- AI suggestions via OpenAI-compatible endpoint ----------


def test_suggest_graceful_without_server(tmp_path, capsys):
    # Nothing listens on port 1; tool must stay friendly, no crash.
    csv_file = use_fixture(tmp_path, "messy.csv")
    code = run_cli(
        "suggest",
        str(csv_file),
        "--base-url",
        "http://127.0.0.1:1/v1",
        "--timeout",
        "1",
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Rule-based suggestions" in out
    assert "customer_name" in out
    assert "no answer" in out


def test_suggest_uses_requestable_fake_endpoint(tmp_path, capsys, monkeypatch):
    # Fake any OpenAI-compatible server to test the happy path offline.
    calls = {}

    def fake_request(base_url, model, prompt, timeout=20):
        calls["base_url"] = base_url
        calls["model"] = model
        return {"Email": "email_address"}

    monkeypatch.setattr(sugg, "request_llm_suggestions", fake_request)
    csv_file = use_fixture(tmp_path, "messy.csv")
    code = run_cli(
        "suggest",
        str(csv_file),
        "--base-url",
        "http://localhost:1234/v1",
        "--model",
        "the-model-name",
    )
    out = capsys.readouterr().out
    assert code == 0
    assert calls["base_url"] == "http://localhost:1234/v1"
    assert calls["model"] == "the-model-name"
    assert "http://localhost:1234/v1" in out
    assert '"Email": "email_address"' in out  # usable JSON in the reply


def test_request_llm_suggestions_payload_shape(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"a":"b"}'}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["data"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(sugg.urllib.request, "urlopen", fake_urlopen)
    result = sugg.request_llm_suggestions(
        "http://localhost:11434/v1", "llama3.2", "hello!"
    )
    assert result == {"a": "b"}
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["data"]["model"] == "llama3.2"
    assert captured["data"]["messages"][0]["content"] == "hello!"
    assert "api_key" not in json.dumps(captured["data"])


def test_default_endpoint_targets_local_ollama():
    assert sugg.DEFAULT_BASE_URL == "http://localhost:11434/v1"


# ---------- version/help surfaces ----------


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli("--version")
    assert exc.value.code == 0
    assert "csvclean" in capsys.readouterr().out


def test_help_mentions_command_names(capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli("--help")
    out = capsys.readouterr().out
    assert exc.value.code == 0
    assert {"profile", "clean", "suggest"} <= {w for w in out.replace(",", " ").split()}


def clean_final_ok():
    return True

