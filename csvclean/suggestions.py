"""Optional AI column-name suggestions via any OpenAI-compatible server.

Default target is a local Ollama server (http://localhost:11434/v1).
Any base URL works - this tool deliberately never asks for, stores, or
sends an API key. If no server is reachable, we still give you honest
rule-based suggestions, no network needed.
"""

import json
import re
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2"
DEFAULT_TIMEOUT = 20


def collect_samples(headers, rows, per_column=3):
    samples = {}
    for i, header in enumerate(headers):
        values = []
        for row in rows:
            cell = row[i] if i < len(row) else ""
            cell = str(cell).strip()
            if cell and cell not in values:
                values.append(cell)
            if len(values) >= per_column:
                break
        samples[header] = values
    return samples


def local_suggestions(headers):
    """Rule-based hints: no LLM required. Good bones, honest limits."""
    suggestions = {}
    for header in headers:
        snake = re.sub(r"[^\w]+", "_", header.strip()).strip("_").lower()
        snake = re.sub(r"_+", "_", snake)
        if snake and snake != header.strip():
            suggestions[header] = snake
    return suggestions


def build_prompt(headers, samples):
    lines = []
    for header, values in samples.items():
        shown = ", ".join(repr(v) for v in values) or "(no values)"
        lines.append(f"- {header}: {shown}")
    sample_text = "\n".join(lines)
    return (
        "You will rename messy CSV column headers to clean, human-friendly ones.\n"
        "Rules:\n"
        "1. Reply with ONLY a single JSON object mapping every original header "
        "to its new name. No explanation, no markdown fences.\n"
        "2. New names: lower snake_case, no spaces or punctuation, short but "
        "meaningful.\n"
        "3. Keep every original column; never invent extra ones.\n"
        "Columns and a few sample values:\n"
        f"{sample_text}\n"
        "Reply with the JSON object only."
    )


def extract_json_mapping(text):
    """Pull a dict of strings out of an LLM reply, tolerating chatter."""
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return None
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    clean = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            clean[k] = v.strip()
    return clean or None


def request_llm_suggestions(base_url, model, prompt, timeout=DEFAULT_TIMEOUT):
    """Call an OpenAI-compatible /chat/completions endpoint. No keys, ever."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    choice = (body.get("choices") or [])[0]
    content = (choice.get("message") or {}).get("content", "")
    return extract_json_mapping(content)
