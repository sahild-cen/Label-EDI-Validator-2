"""
Label Validation Engine — detect_by based
==========================================
Matches rules from MongoDB against raw ZPL data using the detect_by field.
No hardcoded field names. Presence-only validation.

Each rule in MongoDB has:
  {
    "field": "maxicode",
    "required": true,
    "detect_by": "zpl_command:^BD",
    "description": "MaxiCode must be present"
  }

The detect_by value tells this validator exactly how to find
the field on the label. Detection types:

  zpl_command:^BD          — check if ZPL command exists in script
  barcode_data:^1Z         — check if any barcode data matches regex
  barcode_type:MAXICODE    — check if barcode type exists
  text_prefix:DATE:        — check if any text starts with prefix
  text_contains:phrase     — check if any text contains phrase
  text_pattern:regex       — check if any text matches regex
  text_exact:A|B|C         — check if any text equals one of these values
  graphic:GFA              — check if graphic element exists
  spatial:ship_from        — check if text blocks exist in ship-from area
  spatial:ship_to          — check if SHIP TO marker and address blocks exist
"""

import re
from typing import Dict, Any, List, Optional, Tuple


def validate_label_against_rules(raw_data: Dict, rules: Dict, carrier_name: str = "") -> Dict:
    """
    Validate a parsed ZPL label against rules from MongoDB.
    
    Args:
        raw_data: output from parse_zpl_to_raw() — contains text_blocks,
                  barcodes, graphics, zpl_commands, raw_texts
        rules: the label_rules dict from MongoDB (field_formats, required_fields)
        carrier_name: for correction lookups
    
    Returns:
        {
            "status": "PASS" or "FAIL",
            "errors": [...],
            "matched_fields": {...},  # what was found and how
            "compliance_score": float
        }
    """
    errors = []
    matched = {}
    total_rules = 0
    passed_rules = 0

    field_formats = rules.get("field_formats", {})

    for field_name, rule in field_formats.items():
        # Skip non-data fields
        if field_name == "barcode" and rule.get("format"):
            continue

        required = rule.get("required", False)
        detect_by = rule.get("detect_by", "")
        description = rule.get("description", "")

        if not required:
            continue

        total_rules += 1

        # Try to find this field on the label
        found, found_value, method_used = _detect_field(raw_data, detect_by, field_name, description)

        if found:
            passed_rules += 1
            matched[field_name] = {
                "value": found_value[:100] if found_value else "present",
                "method": method_used,
            }
        else:
            errors.append({
                "field": field_name,
                "expected": "Required field",
                "actual": "Not found",
                "description": f"{field_name} not found on label. {description}",
                "detect_by": detect_by,
            })

    score = round(passed_rules / total_rules, 2) if total_rules > 0 else 1.0
    status = "PASS" if not errors else "FAIL"

    return {
        "status": status,
        "errors": errors,
        "matched_fields": matched,
        "compliance_score": score,
        "total_rules_checked": total_rules,
        "rules_passed": passed_rules,
    }


def _detect_field(raw_data: Dict, detect_by: str, field_name: str, description: str) -> Tuple[bool, str, str]:
    """
    Try to find a field on the label using the detect_by instruction.
    
    Returns: (found: bool, value: str, method_used: str)
    """
    texts = raw_data.get("raw_texts", [])
    barcodes = raw_data.get("barcodes", [])
    graphics = raw_data.get("graphics", [])
    zpl_commands = raw_data.get("zpl_commands", [])
    text_blocks = raw_data.get("text_blocks", [])

    if not detect_by:
        # No detect_by — try auto-detection as fallback
        return _auto_detect(raw_data, field_name, description)

    # Parse detect_by format: "type:value"
    if ":" not in detect_by:
        return _auto_detect(raw_data, field_name, description)

    detect_type, detect_value = detect_by.split(":", 1)
    detect_type = detect_type.strip().lower()
    detect_value = detect_value.strip()

    # ── ZPL command detection ──
    if detect_type == "zpl_command":
        cmd = detect_value  # e.g., "^BD", "^GFA", "^B7"
        if cmd in zpl_commands:
            return True, cmd, f"zpl_command:{cmd}"
        # Also check raw script for the command
        return False, "", ""

    # ── Barcode data detection ──
    if detect_type == "barcode_data":
        pattern = detect_value  # e.g., "^1Z", "^42[01]"
        for bc in barcodes:
            try:
                if re.match(pattern, bc["data"]):
                    return True, bc["data"][:50], f"barcode_data:{bc['type']}"
            except re.error:
                if bc["data"].startswith(pattern.lstrip("^")):
                    return True, bc["data"][:50], f"barcode_data:{bc['type']}"
        return False, "", ""

    # ── Barcode type detection ──
    if detect_type == "barcode_type":
        btype = detect_value.upper()  # e.g., "MAXICODE", "CODE128"
        for bc in barcodes:
            if bc["type"] == btype:
                return True, bc["data"][:50], f"barcode_type:{btype}"
        return False, "", ""

    # ── Text prefix detection ──
    if detect_type == "text_prefix":
        prefix = detect_value.upper()  # e.g., "DATE:", "BILLING:", "SHP#:"
        for t in texts:
            if t.upper().strip().startswith(prefix):
                return True, t.strip(), f"text_prefix:{prefix}"
        return False, "", ""

    # ── Text contains detection ──
    if detect_type == "text_contains":
        phrase = detect_value.lower()  # e.g., "shipper agrees"
        for t in texts:
            if phrase in t.lower():
                return True, t[:80], f"text_contains:{detect_value}"
        return False, "", ""

    # ── Text exact match detection ──
    if detect_type == "text_exact":
        values = [v.strip().upper() for v in detect_value.split("|")]
        for t in texts:
            if t.strip().upper() in values:
                return True, t.strip(), f"text_exact:{t.strip()}"
        return False, "", ""

    # ── Text regex pattern detection ──
    if detect_type == "text_pattern":
        pattern = detect_value  # e.g., "^[A-Z]{2,3} \d{3} \d-\d{2}$"
        for t in texts:
            try:
                if re.match(pattern, t.strip()):
                    return True, t.strip(), f"text_pattern:{pattern[:30]}"
            except re.error:
                pass
        return False, "", ""

    # ── Graphic detection ──
    if detect_type == "graphic":
        gtype = detect_value.upper()  # e.g., "GFA"
        for g in graphics:
            if g["type"] == gtype:
                return True, f"graphic:{g['total_bytes']}bytes", f"graphic:{gtype}"
        return False, "", ""

    # ── Spatial detection ──
    if detect_type == "spatial":
        area = detect_value.lower()
        if area == "ship_from":
            # Ship-from is top-left of label, small font
            ship_to_y = _find_ship_to_y(text_blocks)
            if ship_to_y:
                from_blocks = [b for b in text_blocks if b["y"] < ship_to_y and b["x"] < 400]
                if from_blocks:
                    return True, f"{len(from_blocks)} text blocks", "spatial:ship_from"
            else:
                # No SHIP TO marker — check if there's content in top-left
                top_blocks = [b for b in text_blocks if b["y"] < 150 and b["x"] < 400]
                if top_blocks:
                    return True, f"{len(top_blocks)} text blocks", "spatial:ship_from"
            return False, "", ""

        if area == "ship_to":
            ship_to_y = _find_ship_to_y(text_blocks)
            if ship_to_y:
                to_blocks = [b for b in text_blocks
                             if b["x"] >= 200
                             and b["y"] >= ship_to_y - 30
                             and b["y"] < ship_to_y + 160]
                if to_blocks:
                    return True, f"{len(to_blocks)} text blocks", "spatial:ship_to"
            return False, "", ""

    # Unknown detect_by type — try auto-detect
    return _auto_detect(raw_data, field_name, description)


def _auto_detect(raw_data: Dict, field_name: str, description: str) -> Tuple[bool, str, str]:
    """
    Fallback auto-detection when detect_by is missing or unrecognized.
    Tries common patterns based on the field name and description.
    """
    texts = raw_data.get("raw_texts", [])
    barcodes = raw_data.get("barcodes", [])
    zpl_commands = raw_data.get("zpl_commands", [])
    graphics = raw_data.get("graphics", [])

    name_lower = field_name.lower()
    desc_lower = description.lower()

    # Auto-detect by field name patterns
    if "maxicode" in name_lower:
        if "^BD" in zpl_commands:
            return True, "^BD present", "auto:zpl_command"
        for bc in barcodes:
            if bc["type"] == "MAXICODE":
                return True, bc["data"][:30], "auto:barcode_type"

    if "service_icon" in name_lower or "graphic" in name_lower:
        if graphics:
            return True, f"{len(graphics)} graphic(s)", "auto:graphic"

    if "postal_barcode" in name_lower:
        for bc in barcodes:
            if bc["data"].startswith("420") or bc["data"].startswith("421"):
                return True, bc["data"][:30], "auto:barcode_data"

    if "pdf417" in name_lower:
        if "^B7" in zpl_commands:
            return True, "^B7 present", "auto:zpl_command"

    # Auto-detect by common text prefixes
    prefix_map = {
        "billing": "BILLING:",
        "description": "DESC:",
        "desc": "DESC:",
        "goods": "DESC:",
        "tracking": "TRACKING #:",
        "shp_number": "SHP#:",
        "shipment_number": "SHP#:",
        "shipment_date": "DATE:",
        "date": "DATE:",
        "shipment_weight": "SHP WT:",
        "routing_version": "979.",
        "urc_version": "979.",
    }

    for keyword, prefix in prefix_map.items():
        if keyword in name_lower:
            for t in texts:
                if t.upper().strip().startswith(prefix):
                    return True, t.strip()[:50], f"auto:text_prefix:{prefix}"

    # Auto-detect by description keywords
    if "international" in desc_lower and "notice" in desc_lower:
        for t in texts:
            if "shipper agrees" in t.lower():
                return True, t[:50], "auto:text_contains"

    if "routing code" in desc_lower and "version" not in desc_lower:
        for t in texts:
            if re.match(r"^[A-Z]{2,3}\s+\d{3}\s+\d-\d{2}$", t.strip()):
                return True, t.strip(), "auto:text_pattern"

    if "service title" in desc_lower or "service_title" in name_lower:
        for t in texts:
            upper = t.upper().strip()
            if any(upper.startswith(p) for p in ["UPS ", "DHL ", "FEDEX ", "TNT "]):
                return True, upper, "auto:service_keyword"

    if "package count" in desc_lower or "package_count" in name_lower or "piece_count" in name_lower:
        for t in texts:
            if re.search(r"\d+\s+OF\s+(\d+|_)", t, re.IGNORECASE):
                return True, t.strip(), "auto:text_pattern"

    # Generic: try to find field name as a keyword in text blocks
    name_words = name_lower.replace("_", " ").split()
    for t in texts:
        t_lower = t.lower()
        if all(w in t_lower for w in name_words if len(w) > 2):
            return True, t[:50], "auto:keyword_match"

    return False, "", ""


def _find_ship_to_y(text_blocks: list) -> Optional[float]:
    """Find the Y position of the SHIP TO marker."""
    for i, block in enumerate(text_blocks):
        text = block["text"].upper().strip()
        if text in ("SHIP", "SHIP TO:", "SHIP TO"):
            return block["y"]
    return None