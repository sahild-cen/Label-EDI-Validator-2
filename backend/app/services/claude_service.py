import os
import re
import json
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

endpoint = os.getenv("CLAUDE_ENDPOINT")
deployment_name = os.getenv("CLAUDE_DEPLOYMENT")
api_key = os.getenv("CLAUDE_API_KEY")

client = None

try:
    from anthropic import AnthropicFoundry
    client = AnthropicFoundry(api_key=api_key, base_url=endpoint)
    print("Claude client initialized (AnthropicFoundry)")
except ImportError:
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        print("Claude client initialized (Anthropic)")
    except ImportError:
        print("No Anthropic client available.")


def extract_json_from_text(text):
    """Robustly extract JSON from Claude response text."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    json_text = match.group(0)

    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", json_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            print("JSON decode error after cleanup")
            return None


def is_valid_regex(pattern):
    """Reject invalid or impossible regex patterns."""
    if not pattern or not pattern.strip():
        return False
    try:
        re.compile(pattern)
    except re.error:
        return False
    quants = re.findall(r"\{(\d+),(\d+)\}", pattern)
    for min_val, max_val in quants:
        if int(min_val) > int(max_val):
            return False
    return True


def _build_prompt(chunk, section_title=""):
    """
    Pass 1 prompt: Extract candidate rules broadly.
    Pass 2 (rule_validator.py) will do the precise filtering.
    """
    context = ""
    if section_title:
        context = ' (from section: "' + section_title + '")'

    lines = [
        "You are an expert in logistics carrier label and EDI specifications.",
        "",
        "Extract validation rules from the following specification text" + context + ".",
        "",
        "For each rule, determine:",
        "- field_name: a short snake_case name for the data field",
        "- required: true ONLY if the spec explicitly says mandatory/must. Otherwise false.",
        "- format: brief format description if applicable",
        "- regex: a regex pattern ONLY if the spec clearly defines a specific format. Otherwise empty string.",
        "- description: concise rule description",
        "",
        "IMPORTANT:",
        "- Respect the spec's mandatory/optional/conditional distinctions",
        "- Do NOT invent regex patterns that aren't clearly specified",
        "- Make sure regex min<=max in quantifiers",
        "- Maximum 15 rules per chunk",
        "",
        'Return STRICT JSON only:',
        '{"rules": [{"field_name": "<n>", "required": true_or_false, "format": "<>", "regex": "<>", "description": "<>"}]}',
        "",
        'If no rules found: {"rules": []}',
        "",
        "TEXT:",
        chunk,
    ]

    return "\n".join(lines)


def extract_rules_from_chunk(chunk, section_title=""):
    """Pass 1: Extract candidate rules from a text chunk."""
    if not client:
        print("Claude client not initialized")
        return []

    prompt = _build_prompt(chunk, section_title)

    try:
        response = client.messages.create(
            model=deployment_name,
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        if not response.content:
            return []

        text = response.content[0].text
        data = extract_json_from_text(text)

        if not data:
            print("Failed to parse JSON from Claude response")
            return []

        rules = data.get("rules", [])

        # Basic regex validation (Pass 2 will do deeper validation)
        for rule in rules:
            regex = rule.get("regex", "")
            if regex and not is_valid_regex(regex):
                rule["regex"] = ""

        return rules

    except Exception as e:
        print("Claude extraction error: {}".format(str(e)))
        return []