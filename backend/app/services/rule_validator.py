"""
Rule Validator - Pass 2 AI Validation with Learning Loop
=========================================================
"""

import re
import json
from typing import List, Dict, Optional

import app.services.claude_service as cs
from app.services.claude_service import extract_json_from_text


_corrections_cache: List[Dict] = []


def load_corrections(db=None):
    global _corrections_cache
    if db is None:
        return
    try:
        _corrections_cache = list(db.validation_corrections.find(
            {}, {"_id": 0}
        ).sort("timestamp", -1).limit(100))
        print(f"[Validator] Loaded {len(_corrections_cache)} past corrections")
    except Exception as e:
        print(f"[Validator] Warning: could not load corrections: {e}")


def save_correction(db, carrier: str, field: str, error_type: str,
                    original_rule: dict = None, corrected_rule: dict = None,
                    reason: str = ""):
    if db is None:
        return
    try:
        from datetime import datetime
        doc = {
            "carrier": carrier.lower(),
            "field": field,
            "error_type": error_type,
            "original_rule": original_rule,
            "corrected_rule": corrected_rule,
            "reason": reason,
            "timestamp": datetime.utcnow()
        }
        db.validation_corrections.insert_one(doc)
        _corrections_cache.insert(0, doc)
        if len(_corrections_cache) > 100:
            _corrections_cache.pop()
    except Exception as e:
        print(f"[Validator] Warning: could not save correction: {e}")


def sanity_check_rules(rules: List[Dict], carrier_name: str = "") -> List[Dict]:
    cleaned = []
    for rule in rules:
        field = rule.get("field", "").lower().strip()
        regex = rule.get("regex", "")
        if not field or len(field) > 50:
            continue
        if regex:
            rule["regex"] = _validate_regex_syntax(regex)
        cleaned.append(rule)
    return cleaned


def _validate_regex_syntax(regex: str) -> str:
    if not regex or not regex.strip():
        return ""
    try:
        re.compile(regex)
    except re.error:
        return ""
    for min_v, max_v in re.findall(r"\{(\d+),(\d+)\}", regex):
        if int(min_v) > int(max_v):
            return ""
    return regex


def _build_few_shot_examples(carrier_name: str = "") -> str:
    if not _corrections_cache:
        return ""
    carrier_lower = carrier_name.lower() if carrier_name else ""
    relevant = []
    for c in _corrections_cache:
        if c.get("carrier", "") == carrier_lower:
            relevant.append(c)
    for c in _corrections_cache:
        if c.get("carrier", "") != carrier_lower and len(relevant) < 10:
            relevant.append(c)
    if not relevant:
        return ""
    examples = "\n\nLEARNED FROM PAST CORRECTIONS:\n"
    for c in relevant[:8]:
        error_type = c.get("error_type", "")
        field = c.get("field", "")
        reason = c.get("reason", "")
        if error_type == "false_positive":
            examples += f"- '{field}' was wrongly DATA_VALIDATION. {reason}. → SPEC_GUIDELINE.\n"
        elif error_type == "wrong_regex":
            orig = c.get("original_rule", {}).get("regex", "")
            fixed = c.get("corrected_rule", {}).get("regex", "")
            examples += f"- '{field}' regex '{orig}' was wrong. Correct: '{fixed}'\n"
        elif error_type == "wrong_required":
            examples += f"- '{field}' was wrongly required. {reason}\n"
        elif error_type == "missing_field":
            examples += f"- '{field}' should be DATA_VALIDATION but was missed. {reason}\n"
    return examples


def validate_rules_with_ai(rules: List[Dict], carrier_name: str = "") -> List[Dict]:
    if not rules:
        return []

    if not cs.client:
        print("Claude client not available for Pass 2, returning candidates as-is")
        return rules[:25]

    # Build candidate list — FIXED format string with all fields
    rules_text = ""
    for i, rule in enumerate(rules):
        rules_text += (
            f"{i+1}. field='{rule.get('field', '')}'"
            f" | required={rule.get('required', False)}"
            f" | regex='{rule.get('regex', '')}'"
            f" | detect_by='{rule.get('detect_by', '')}'"
            f" | description='{rule.get('description', '')}'\n"
        )

    carrier_context = f" for carrier '{carrier_name}'" if carrier_name else ""
    few_shot = _build_few_shot_examples(carrier_name)

    prompt_lines = [
        "You are a logistics label validation expert.",
        "",
        f"Below are candidate validation rules from a carrier specification{carrier_context}.",
        "",
        "YOUR TASK: Classify each rule, ensure detect_by is filled, set required correctly.",
        "",
        "═══ CLASSIFICATION ═══",
        "",
        "DATA_VALIDATION = A field VISIBLE on the printed label that can be checked for presence.",
        "  Includes: tracking numbers, service titles, icons, addresses, barcodes (as presence),",
        "  weight, package count, billing, description of goods, dates, routing codes,",
        "  documentation indicators, logos, postal barcodes, MaxiCode, shipping notices, etc.",
        "",
        "SPEC_GUIDELINE = Physical specs, encoding internals, sub-components.",
        "  Includes: font sizes, barcode dimensions, quiet zones, check digit algorithms,",
        "  internal data positions, highlight bar thickness, etc.",
        "",
        "═══ detect_by — MUST BE FILLED FOR EVERY DATA_VALIDATION RULE ═══",
        "",
        "detect_by tells the validator how to find the field on a ZPL label.",
        "If detect_by is empty in the input, YOU MUST fill it based on the field type.",
        "",
        "Formats:",
        "  zpl_command:^BD             — ZPL command (MaxiCode=^BD, PDF417=^B7)",
        "  barcode_data:^1Z            — barcode data prefix (UPS tracking=^1Z, DHL=^JD, postal=^42[01])",
        "  text_prefix:BILLING:        — text starts with (DATE:, DESC:, SHP#:, TRACKING #:, BILLING:, SHP WT:, REF)",
        "  text_contains:Shipper agrees — text contains phrase",
        "  text_pattern:^regex$         — text matches regex (routing codes, version strings, package counts)",
        "  text_exact:EDI|DOC|INV|KEY  — text equals one of these values",
        "  graphic:GFA                 — graphic image (service icons, logos)",
        "  spatial:ship_from           — address block in ship-from area of label",
        "  spatial:ship_to             — address block in ship-to area of label",
        "",
        "Common mappings:",
        "  maxicode           → zpl_command:^BD",
        "  postal_barcode     → barcode_data:^42[01]",
        "  tracking barcode   → barcode_data:^1Z (UPS) or ^JD (DHL) or ^\\d{12} (FedEx)",
        "  service_icon       → graphic:GFA",
        "  ups_logo / logo    → graphic:GFA",
        "  billing            → text_prefix:BILLING:",
        "  date / shipment_date → text_prefix:DATE:",
        "  description_of_goods → text_prefix:DESC:",
        "  shipment_number    → text_prefix:SHP#:",
        "  tracking_number_hr → text_prefix:TRACKING #:",
        "  piece_count        → text_pattern:\\d+ OF (\\d+|_)",
        "  routing_code       → text_pattern:^[A-Z]{2,3} \\d{3} \\d-\\d{2}$",
        "  routing_instruction / documentation_indicator → text_exact:EDI|DOC|INV|KEY|POA|EDI-PULL",
        "  sender_address     → spatial:ship_from",
        "  receiver_address   → spatial:ship_to",
        "  service_type/title → text_pattern:^(UPS|DHL|FEDEX|TNT) ",
        "  weight             → text_pattern:^\\d+\\.?\\d*\\s+(KG|LBS?)$",
        "  country            → text_pattern:^(GERMANY|FRANCE|SPAIN|...|[A-Z]{2})$  or spatial detection",
        "  postal_code        → text_pattern:^\\d{4,5}[- ]",
        "  version/control    → text_pattern:^\\d{2,3}\\.\\w\\.\\d{3}",
        "  int'l notice       → text_contains:Shipper agrees",
        "  pdf417             → zpl_command:^B7",
        "",
        "═══ REQUIRED LOGIC ═══",
        "",
        "- Fields with no regex (presence-only checks) → required=true by default",
        "- Fields listed as 'Carrier Required Information' → required=true",
        "- Fields conditional on service/region → required=false",
        "- When in doubt → required=true",
        "",
        "═══ REGEX ═══",
        "",
        "- Clear regex to empty for presence-only fields",
        "- Only keep regex for specific format requirements (tracking number format, date format)",
        "- If regex is too restrictive, clear it",
    ]

    if few_shot:
        prompt_lines.append(few_shot)

    prompt_lines.extend([
        "",
        "═══ OUTPUT ═══",
        "",
        "Return STRICT JSON only:",
        '{"validated_rules": [{"index": N, "category": "DATA_VALIDATION", "field": "...", "required": true/false, "regex": "...", "detect_by": "type:value", "description": "...", "reason": "brief"}]}',
        "",
        "CRITICAL: detect_by MUST NOT be empty for any DATA_VALIDATION rule.",
        "Only include DATA_VALIDATION rules. Skip SPEC_GUIDELINE entirely.",
        "Maximum 25 DATA_VALIDATION rules.",
        "",
        "CANDIDATE RULES:",
        rules_text,
    ])

    prompt = "\n".join(prompt_lines)

    try:
        response = cs.client.messages.create(
            model=cs.deployment_name,
            max_tokens=4000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        if not response.content:
            print("Pass 2: Empty response")
            return rules[:25]

        text = response.content[0].text
        data = extract_json_from_text(text)

        if not data or "validated_rules" not in data:
            print("Pass 2: Could not parse response")
            return rules[:25]

        validated = data["validated_rules"]

        final_rules = []
        for v in validated:
            if v.get("category") != "DATA_VALIDATION":
                continue

            rule = {
                "field": v.get("field", ""),
                "required": v.get("required", False),
                "regex": v.get("regex", ""),
                "detect_by": v.get("detect_by", ""),
                "description": v.get("description", ""),
            }

            # Regex syntax check
            if rule["regex"]:
                rule["regex"] = _validate_regex_syntax(rule["regex"])

            # If no regex and no detect_by, skip — can't validate this field
            if not rule["regex"] and not rule["detect_by"]:
                print(f"  [Pass 2] Skipping '{rule['field']}' — no detect_by and no regex")
                continue

            if rule["field"]:
                final_rules.append(rule)

        print(f"[Pass 2] {len(rules)} candidates -> {len(final_rules)} validated rules")
        for r in final_rules:
            print(f"  -> {r['field']:30s} required={str(r['required']):5s} detect_by='{r['detect_by']}'")

        return final_rules

    except Exception as e:
        print(f"Pass 2 error: {str(e)}")
        return rules[:25]