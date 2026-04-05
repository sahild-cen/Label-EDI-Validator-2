"""
Rule Validator - Pass 2 AI Validation with Learning Loop
=========================================================
Takes candidate rules from Pass 1 and classifies them via Claude.

NEW: Feedback/learning system:
1. Loads past corrections as few-shot examples for the prompt
2. Uses golden rules when available (skips re-extraction)
3. Records false positives to prevent future repeats
4. Post-validation sanity checks catch obviously bad rules
"""

import re
import json
from typing import List, Dict, Optional

# Reuse the same client from claude_service
import app.services.claude_service as cs
from app.services.claude_service import extract_json_from_text


# ═══════════════════════════════════════════════════════════════
# CORRECTIONS DATABASE INTERFACE
# ═══════════════════════════════════════════════════════════════

# In-memory cache of past corrections
_corrections_cache: List[Dict] = []


def load_corrections(db=None):
    """
    Load past correction records from MongoDB at startup.

    Collection: validation_corrections
    Schema: {
        carrier: str,
        field: str,
        error_type: "false_positive" | "wrong_regex" | "wrong_required" | "missing_field",
        original_rule: {...},
        corrected_rule: {...} | null,
        reason: str,
        timestamp: datetime
    }
    """
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
    """Save a correction to MongoDB for future learning."""
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
        # Keep cache bounded
        if len(_corrections_cache) > 100:
            _corrections_cache.pop()
        print(f"[Validator] Saved correction: {carrier}/{field} ({error_type})")
    except Exception as e:
        print(f"[Validator] Warning: could not save correction: {e}")


# ═══════════════════════════════════════════════════════════════
# POST-EXTRACTION SANITY CHECKS
# ═══════════════════════════════════════════════════════════════

def sanity_check_rules(rules: List[Dict], carrier_name: str = "") -> List[Dict]:
    """
    Post-extraction sanity checks that catch obviously bad rules
    BEFORE they reach Pass 2. This reduces load on the AI classifier.

    Checks:
    1. Regex plausibility per field type
    2. Sub-constraint detection (field names that are properties of other fields)
    3. Duplicate/near-duplicate field names
    4. Overly specific or carrier-internal fields
    """
    cleaned = []
    carrier_lower = carrier_name.lower()

    for rule in rules:
        field = rule.get("field", "").lower().strip()
        regex = rule.get("regex", "")

        # Check 1: Sub-constraint detection
        if _is_sub_constraint(field):
            print(f"  [Sanity] Removed sub-constraint: '{field}'")
            continue

        # Check 2: Regex plausibility
        if regex:
            rule["regex"] = _sanitize_regex(field, regex, carrier_lower)

        # Check 3: Skip overly generic or meta fields
        if _is_meta_field(field):
            print(f"  [Sanity] Removed meta field: '{field}'")
            continue

        # Check 4: Skip duplicate-ish fields (e.g., both "city" and "ship_to_city")
        # This is handled later by dedup, but we can flag here

        cleaned.append(rule)

    return cleaned


def _is_sub_constraint(field: str) -> bool:
    """
    Detect field names that are sub-constraints of a parent field.
    e.g., license_plate_length, address_line_max_characters, tracking_number_check_digit
    """
    sub_constraint_suffixes = [
        "_length", "_characters", "_prefix", "_suffix",
        "_format", "_structure", "_checkdigit", "_check_digit",
        "_encoding", "_indicator", "_symbology", "_type",
        "_x_dimension", "_height", "_width", "_quiet_zone",
        "_min_length", "_max_length", "_max_characters",
        "_min_characters", "_allowed_characters",
    ]
    for suffix in sub_constraint_suffixes:
        if field.endswith(suffix):
            return True

    # Also catch patterns like "barcode_code128" or "maxicode_mode"
    sub_constraint_patterns = [
        r"^.+_mode\d*$",
        r"^.+_version\d*$",
        r"^.+_error_correction$",
        r"^.+_data_content$",
        r"^.+_font_size$",
    ]
    for pattern in sub_constraint_patterns:
        if re.match(pattern, field):
            return True

    return False


def _sanitize_regex(field: str, regex: str, carrier: str) -> str:
    """
    Fix or reject obviously wrong regexes.
    Returns corrected regex or empty string if unfixable.
    """
    # Validate syntax
    try:
        re.compile(regex)
    except re.error:
        return ""

    # Check impossible quantifiers
    for min_v, max_v in re.findall(r"\{(\d+),(\d+)\}", regex):
        if int(min_v) > int(max_v):
            return ""

    # Field-specific checks
    if "tracking" in field or "shipment" in field or "waybill" in field:
        # Tracking numbers are always 8+ chars, usually 12-35
        for min_v, max_v in re.findall(r"\{(\d+),(\d+)\}", regex):
            if int(max_v) < 8:
                print(f"  [Sanity] Tracking regex too short: '{regex}'")
                return ""

    if "postal" in field or "zip" in field or "postcode" in field:
        # Postal codes vary 3-10 chars worldwide
        if regex in (r"^[A-Za-z0-9]{5}$", r"^\d{5}$"):
            print(f"  [Sanity] Postal code regex too rigid: '{regex}'")
            return r"^[A-Z0-9 \-]{3,10}$"

    if "city" in field:
        # Cities can be 1-50+ chars, limit of 20 is wrong
        for min_v, max_v in re.findall(r"\{(\d+),(\d+)\}", regex):
            if int(max_v) < 30:
                print(f"  [Sanity] City regex too short: '{regex}'")
                return ""

    return regex


def _is_meta_field(field: str) -> bool:
    """Detect meta/structural field names that aren't real label fields."""
    meta_keywords = [
        "iso_standard", "specification", "example", "guide",
        "implementation", "document", "version", "copyright",
        "appendix", "annex", "glossary", "definition", "index",
        "note", "remark", "comment", "instruction",
    ]
    return any(kw in field for kw in meta_keywords)


# ═══════════════════════════════════════════════════════════════
# FEW-SHOT EXAMPLE GENERATION
# ═══════════════════════════════════════════════════════════════

def _build_few_shot_examples(carrier_name: str = "") -> str:
    """
    Build few-shot examples from past corrections to inject into the Pass 2 prompt.
    This is the key learning mechanism — past mistakes become teaching examples.
    """
    if not _corrections_cache:
        return ""

    carrier_lower = carrier_name.lower() if carrier_name else ""

    # Prioritize corrections for this carrier, then general ones
    relevant = []
    for c in _corrections_cache:
        if c.get("carrier", "") == carrier_lower:
            relevant.append(c)
    # Add some general corrections too
    for c in _corrections_cache:
        if c.get("carrier", "") != carrier_lower and len(relevant) < 10:
            relevant.append(c)

    if not relevant:
        return ""

    examples = "\n\nLEARNED FROM PAST CORRECTIONS (apply these lessons):\n"
    for i, c in enumerate(relevant[:8]):
        error_type = c.get("error_type", "")
        field = c.get("field", "")
        reason = c.get("reason", "")

        if error_type == "false_positive":
            examples += f"- Field '{field}' was incorrectly classified as DATA_VALIDATION. "
            examples += f"Reason: {reason}. Classify as SPEC_GUIDELINE.\n"
        elif error_type == "wrong_regex":
            orig = c.get("original_rule", {}).get("regex", "")
            fixed = c.get("corrected_rule", {}).get("regex", "")
            examples += f"- Field '{field}' had wrong regex '{orig}'. Correct: '{fixed}'\n"
        elif error_type == "wrong_required":
            examples += f"- Field '{field}' was incorrectly marked as required. {reason}\n"
        elif error_type == "missing_field":
            examples += f"- Field '{field}' should be DATA_VALIDATION but was missed. {reason}\n"

    return examples


# ═══════════════════════════════════════════════════════════════
# MAIN PASS 2 VALIDATION
# ═══════════════════════════════════════════════════════════════

def validate_rules_with_ai(rules: List[Dict], carrier_name: str = "") -> List[Dict]:
    """
    Pass 2: Send all candidate rules to Claude for classification.
    Returns only rules classified as DATA_VALIDATION.

    Enhanced with:
    1. Pre-validation sanity checks
    2. Few-shot examples from past corrections
    3. Post-validation regex sanity checks
    """
    if not rules:
        return []

    # Pre-validation sanity checks
    rules = sanity_check_rules(rules, carrier_name)
    print(f"[Pass 2] After sanity checks: {len(rules)} candidates")

    if not cs.client:
        print("Claude client not available for Pass 2, falling back to basic filter")
        return _basic_fallback_filter(rules)

    # Build the rules list for Claude to evaluate
    rules_text = ""
    for i, rule in enumerate(rules):
        rules_text += "{}. field='{}' | required={} | regex='{}' | description='{}'\n".format(
            i + 1,
            rule.get("field", ""),
            rule.get("required", False),
            rule.get("regex", ""),
            rule.get("description", "")
        )

    carrier_context = ""
    if carrier_name:
        carrier_context = f" for carrier '{carrier_name}'"

    # Build few-shot examples from past corrections
    few_shot = _build_few_shot_examples(carrier_name)

    prompt_lines = [
        "You are a logistics label validation expert.",
        "",
        f"Below is a list of candidate validation rules extracted from a carrier specification document{carrier_context}.",
        "",
        "YOUR TASK: Classify each rule into exactly one of two categories:",
        "",
        "DATA_VALIDATION = A rule that can be verified by reading the DATA CONTENT of a shipping label.",
        "  These are TOP-LEVEL fields whose VALUE can be checked against a pattern or required/not-required.",
        "  Examples: tracking_number format, postal_code presence, country_code, weight, service_type,",
        "  sender_address presence, receiver_address presence, piece_count.",
        "  IMPORTANT: Only include fields that a label parser can INDEPENDENTLY extract and validate.",
        "",
        "SPEC_GUIDELINE = Everything else - physical properties, layout, internal barcode structure,",
        "  sub-components of other fields, conditional rules, encoding specifications.",
        "  Examples: barcode x-dimension, font size, quiet zone, barcode symbology type,",
        "  check digit algorithms, data identifiers, field separators,",
        "  internal routing barcode components, MaxiCode data format,",
        "  anything about HOW data is encoded rather than WHAT the data value should be.",
        "",
        "SUB-CONSTRAINT RULE (CRITICAL):",
        "  If a field describes a PROPERTY or COMPONENT of another field, it is SPEC_GUIDELINE.",
        "  Examples: license_plate_length, license_plate_prefix, address_line_max_characters,",
        "  postal_code_length, tracking_number_check_digit, barcode_height, ups_account_number",
        "  (account number is embedded in tracking number, not a standalone label field).",
        "  Rule of thumb: if the field name implies it's a constraint ON another field,",
        "  or if the value can only be extracted by parsing another field's value,",
        "  classify it as SPEC_GUIDELINE.",
        "",
        "REGEX VALIDATION (CRITICAL):",
        "  For each DATA_VALIDATION rule, verify the regex makes sense:",
        "  - Tracking numbers: must allow 8-35 characters (varies by carrier)",
        "  - Postal codes: must allow 3-10 characters (varies by country)",
        "  - Cities: must allow up to 50+ characters",
        "  - Country codes: 2-3 characters",
        "  - If a regex is too restrictive for international use, SET IT TO EMPTY STRING.",
        "  - If min > max in a quantifier like {33,4}, SET IT TO EMPTY STRING.",
        "",
        "REQUIRED FIELD VALIDATION:",
        "  Only set required=true if the spec says MANDATORY/MUST for ALL shipments.",
        "  If conditional, optional, or only for certain regions/services, set required=false.",
    ]

    # Inject few-shot learning
    if few_shot:
        prompt_lines.append(few_shot)

    prompt_lines.extend([
        "",
        "Return STRICT JSON only:",
        '{"validated_rules": [{"index": 1, "category": "DATA_VALIDATION", "field": "...", "required": true/false, "regex": "...", "description": "...", "reason": "brief reason"}]}',
        "",
        "Only include rules where category is DATA_VALIDATION. Skip all SPEC_GUIDELINE rules entirely.",
        "Maximum 15 DATA_VALIDATION rules. Prefer fewer, higher-quality rules over many low-quality ones.",
        "",
        "CANDIDATE RULES:",
        rules_text,
    ])

    prompt = "\n".join(prompt_lines)

    try:
        response = cs.client.messages.create(
            model=cs.deployment_name,
            max_tokens=3000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        if not response.content:
            print("Pass 2: Empty response from Claude")
            return _basic_fallback_filter(rules)

        text = response.content[0].text
        data = extract_json_from_text(text)

        if not data or "validated_rules" not in data:
            print("Pass 2: Could not parse response")
            return _basic_fallback_filter(rules)

        validated = data["validated_rules"]

        # Build final rules list with post-validation sanity checks
        final_rules = []
        for v in validated:
            if v.get("category") != "DATA_VALIDATION":
                continue

            rule = {
                "field": v.get("field", ""),
                "required": v.get("required", False),
                "regex": v.get("regex", ""),
                "description": v.get("description", ""),
            }

            # Post-validation: reject sub-constraints that slipped through
            if _is_sub_constraint(rule["field"]):
                print(f"  [Pass 2] Post-check rejected sub-constraint: '{rule['field']}'")
                continue

            # Post-validation: regex sanity
            if rule["regex"]:
                rule["regex"] = _sanitize_regex(
                    rule["field"], rule["regex"], carrier_name.lower()
                )

            if rule["field"]:
                final_rules.append(rule)

        print(f"[Pass 2] Claude validated {len(rules)} rules -> {len(final_rules)} DATA_VALIDATION rules kept")

        for r in final_rules:
            print(f"  -> {r['field']} (required={r['required']}, regex={bool(r['regex'])})")

        return final_rules

    except Exception as e:
        print(f"Pass 2 error: {str(e)}")
        return _basic_fallback_filter(rules)


def _basic_fallback_filter(rules: List[Dict]) -> List[Dict]:
    """
    Fallback if Claude Pass 2 fails.
    Uses sub-constraint detection + physical keyword filtering.
    """
    physical_keywords = [
        "font", "size", "height", "width", "position", "orientation",
        "color", "logo", "quiet_zone", "x_dimension", "symbol",
        "quality", "grade", "print", "dimension", "row", "column",
        "aspect", "correction", "encoding", "format_indicator",
        "start_character", "stop_character", "check_digit",
        "data_identifier", "application_identifier", "separator",
        "terminator", "prefix", "suffix", "agency",
        "characters", "length", "structure", "indicator",
        "mode", "symbology", "module",
    ]

    filtered = []
    for rule in rules:
        field = rule.get("field", "").lower()

        if len(field) > 40:
            continue
        if _is_sub_constraint(field):
            continue
        if any(kw in field for kw in physical_keywords):
            continue
        if _is_meta_field(field):
            continue

        # Sanitize regex
        if rule.get("regex"):
            rule["regex"] = _sanitize_regex(field, rule["regex"], "")

        filtered.append(rule)

    return filtered[:15]