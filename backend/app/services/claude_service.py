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


"""
Updated _build_prompt() for claude_service.py
==============================================
Replace your existing _build_prompt() function with this version.

KEY CHANGE: Each extracted rule now includes a "detect_by" field
that tells the validator how to find this element on a ZPL label.

The detect_by is generated ONCE during PDF extraction (spec PDFs
are not customer data). After that, all validation is local
string matching — no AI needed at validation time.
"""


def _build_prompt(chunk, section_title=""):
    """
    Pass 1 prompt: Extract ALL label fields with detect_by instructions.
    Carrier-agnostic — works for any carrier spec PDF.
    """
    context = ""
    if section_title:
        context = f' (from section: "{section_title}")'

    lines = [
        "You are an expert in logistics carrier shipping label specifications and ZPL (Zebra Programming Language).",
        "",
        f"Extract ALL label data fields and validation rules from the following specification text{context}.",
        "",
        "═══ WHAT TO EXTRACT ═══",
        "",
        "Extract every NAMED ELEMENT that must appear on a shipping label.",
        "For each element, determine how a ZPL label parser would DETECT its presence.",
        "",
        "═══ DETECT_BY INSTRUCTIONS ═══",
        "",
        "For each field, provide a detect_by value that tells the validator",
        "how to find this element on a ZPL label. Use one of these formats:",
        "",
        "  zpl_command:^BD         — field is a ZPL barcode/graphic command",
        "                            Use for: MaxiCode (^BD), PDF417 (^B7), graphics (^GFA)",
        "",
        "  barcode_data:^1Z        — field is a barcode whose data matches this regex prefix",
        "                            Use for: tracking barcodes (^1Z for UPS, ^JD for DHL),",
        "                            postal barcodes (^42[01] for UPS postal codes)",
        "",
        "  text_prefix:DATE:       — field is text that starts with this prefix",
        "                            Use for: DATE:, BILLING:, DESC:, SHP#:, SHP WT:,",
        "                            TRACKING #:, REF #:, MRN NUMBER:, FROM:, etc.",
        "",
        "  text_contains:phrase    — field is text containing this phrase (case-insensitive)",
        "                            Use for: international shipping notices, legal text,",
        "                            terms and conditions",
        "",
        "  text_pattern:regex      — field is text matching this regex pattern",
        "                            Use for: routing codes (^[A-Z]{2,3} \\d{3} \\d-\\d{2}$),",
        "                            version strings (^\\d{2,3}\\.\\w\\.\\d{3}),",
        "                            package counts (\\d+ OF \\d+),",
        "                            service titles (^UPS |^DHL |^FEDEX )",
        "",
        "  text_exact:A|B|C        — field is standalone text that equals one of these values",
        "                            Use for: documentation indicators (EDI|DOC|INV|KEY|POA),",
        "                            country names, short codes",
        "",
        "  graphic:GFA             — field is a graphic image element",
        "                            Use for: service icons, logos, visual indicators",
        "",
        "  spatial:ship_from       — field is an address block in the ship-from area",
        "  spatial:ship_to         — field is an address block in the ship-to area",
        "",
        "═══ WHAT TO SKIP ═══",
        "",
        "DO NOT extract physical printing specifications:",
        "  - Font names and sizes (Arial 8pt)",
        "  - Barcode dimensions (x-dimension, bar height, quiet zones)",
        "  - Print DPI, resolution, label stock size",
        "  - Color specs, line thickness",
        "  - Field positioning coordinates",
        "  - Internal barcode encoding (check digit algorithms, data identifiers)",
        "",
        "═══ STRUCTURED TABLES ═══",
        "",
        "Carrier specs often have NUMBERED TABLES listing label elements.",
        "Extract EVERY row as a field. Also look for 'Carrier Required Information' sections.",
        "",
        "═══ FIELD NAMING ═══",
        "",
        "Use the spec's own terminology in snake_case.",
        "  'Service Icon' → 'service_icon'",
        "  'MaxiCode Symbology' → 'maxicode'",
        "  'Postal Barcode' → 'postal_barcode'",
        "  'UPS Routing Code' → 'ups_routing_code'",
        "  'Package Count' → 'package_count'",
        "  'Description of Goods' → 'description_of_goods'",
        "",
        "═══ REQUIRED vs OPTIONAL ═══",
        "",
        "- required=true if: 'required', 'mandatory', 'must appear', 'must print',",
        "  listed under 'Carrier Required Information', appears in numbered table",
        "- required=false if: 'optional', 'conditional', 'when applicable',",
        "  'not required for [region]'",
        "- When in doubt: required=true",
        "",
        "═══ OUTPUT FORMAT ═══",
        "",
        "Return STRICT JSON only:",
        '{"rules": [{"field_name": "snake_case", "required": true/false, "detect_by": "type:value", "description": "from spec"}]}',
        "",
        'If no fields found: {"rules": []}',
        "",
        "Extract up to 25 rules per chunk.",
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