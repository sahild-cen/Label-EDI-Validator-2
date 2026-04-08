import re
import cv2
import numpy as np
import pytesseract
from typing import Dict, Any, List, Optional, Tuple
from app.models.validation import ValidationError
from app.routes.corrections import check_corrections_before_failing


try:
    from pyzbar import pyzbar
except Exception:
    pyzbar = None


def _get_db():
    try:
        from app.database import get_database
        return get_database()
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# MANDATORY FIELD OVERRIDES (async Motor compatible)
# ═══════════════════════════════════════════════════════════════

async def _load_mandatory_overrides(db, carrier_name: str) -> dict:
    """Load user-reported mandatory fields from MongoDB (async Motor)."""
    if db is None:
        return {}
    try:
        carrier_key = carrier_name.lower().strip()
        overrides = {}
        cursor = db.mandatory_field_overrides.find({
            "carrier": carrier_key,
            "required": True,
        })
        docs = await cursor.to_list(length=100)
        for doc in docs:
            overrides[doc["field"]] = {
                "required": True,
                "pattern": doc.get("pattern"),
                "detect_by": doc.get("detect_by", ""),
                "description": doc.get("description", ""),
            }
        if overrides:
            print(f"  [Learned] Loaded {len(overrides)} mandatory override(s) "
                  f"for {carrier_name}: {list(overrides.keys())}")
        return overrides
    except Exception as e:
        print(f"  [Learned] Warning: could not load overrides: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════
# DETECT_BY MATCHING ENGINE
# ═══════════════════════════════════════════════════════════════
# Matches a rule's detect_by instruction against raw ZPL data.
# No hardcoded field names. Works for any carrier.
#
# Detection types:
#   zpl_command:^BD       — ZPL command present in script
#   barcode_data:^1Z      — barcode data matches regex prefix
#   barcode_type:MAXICODE — barcode type exists
#   text_prefix:DATE:     — any text starts with prefix
#   text_contains:phrase  — any text contains phrase
#   text_pattern:regex    — any text matches regex
#   text_exact:A|B|C      — any text equals one of these
#   graphic:GFA           — graphic element exists
#   spatial:ship_from     — text blocks in ship-from area
#   spatial:ship_to       — text blocks after SHIP TO marker

def _detect_field_by_rule(raw_data: dict, detect_by: str,
                          field_name: str, description: str) -> Tuple[bool, str]:
    """
    Try to find a field on the label using detect_by instruction.
    Returns (found, actual_value_or_reason).
    """
    if not raw_data:
        return False, "Not found"

    texts = raw_data.get("raw_texts", [])
    barcodes = raw_data.get("barcodes", [])
    graphics = raw_data.get("graphics", [])
    zpl_commands = raw_data.get("zpl_commands", [])
    text_blocks = raw_data.get("text_blocks", [])

    # If detect_by is provided, use it as primary detection
    if detect_by and ":" in detect_by:
        detect_type, detect_value = detect_by.split(":", 1)
        detect_type = detect_type.strip().lower()
        detect_value = detect_value.strip()

        if detect_type == "zpl_command":
            # Check if command exists in the ZPL commands list
            if detect_value in zpl_commands:
                return True, detect_value
            # Also try substring match (^GFA → ^GF might be in list)
            cmd_prefix = detect_value[:3]
            if any(c.startswith(cmd_prefix) for c in zpl_commands):
                return True, detect_value
            return False, "Not found"

        if detect_type == "barcode_data":
            for bc in barcodes:
                try:
                    if re.match(detect_value, bc["data"]):
                        return True, bc["data"][:50]
                except re.error:
                    if bc["data"].startswith(detect_value.lstrip("^")):
                        return True, bc["data"][:50]
            return False, "Not found"

        if detect_type == "barcode_type":
            btype = detect_value.upper()
            for bc in barcodes:
                if bc["type"] == btype:
                    return True, bc["data"][:50]
            return False, "Not found"

        if detect_type == "text_prefix":
            prefix = detect_value.upper()
            for t in texts:
                if t.upper().strip().startswith(prefix):
                    return True, t.strip()[:60]
            return False, "Not found"

        if detect_type == "text_contains":
            phrase = detect_value.lower()
            for t in texts:
                if phrase in t.lower():
                    return True, t[:60]
            return False, "Not found"

        if detect_type == "text_exact":
            values = [v.strip().upper() for v in detect_value.split("|")]
            for t in texts:
                if t.strip().upper() in values:
                    return True, t.strip()
            return False, "Not found"

        if detect_type == "text_pattern":
            for t in texts:
                try:
                    if re.match(detect_value, t.strip()):
                        return True, t.strip()[:60]
                except re.error:
                    pass
            return False, "Not found"

        if detect_type == "graphic":
            gtype = detect_value.upper()
            for g in graphics:
                if g["type"] == gtype:
                    return True, f"graphic:{g['total_bytes']}bytes"
            return False, "Not found"

        if detect_type == "spatial":
            area = detect_value.lower()
            ship_to_y = _find_ship_to_y(text_blocks)

            if area in ("ship_from", "top_left_block"):
                if ship_to_y:
                    from_blocks = [b for b in text_blocks
                                   if b["y"] < ship_to_y and b["x"] < 400]
                    if from_blocks:
                        return True, f"{len(from_blocks)} text blocks"
                else:
                    top_blocks = [b for b in text_blocks
                                  if b["y"] < 150 and b["x"] < 400]
                    if top_blocks:
                        return True, f"{len(top_blocks)} text blocks"
                return False, "Not found"

            if area in ("ship_to", "ship_to_address"):
                if ship_to_y:
                    to_blocks = [b for b in text_blocks
                                 if b["x"] >= 200
                                 and b["y"] >= ship_to_y - 30
                                 and b["y"] < ship_to_y + 160]
                    if to_blocks:
                        return True, f"{len(to_blocks)} text blocks"
                return False, "Not found"

    # ── Fallback: auto-detection when detect_by is missing ──
    return _auto_detect(raw_data, field_name, description)


def _auto_detect(raw_data: dict, field_name: str, description: str) -> Tuple[bool, str]:
    """
    Fallback auto-detection when detect_by is empty.
    Tries common patterns based on field name and description.
    """
    texts = raw_data.get("raw_texts", [])
    barcodes = raw_data.get("barcodes", [])
    zpl_commands = raw_data.get("zpl_commands", [])
    graphics = raw_data.get("graphics", [])

    name_lower = field_name.lower()
    desc_lower = description.lower()

    # ZPL command auto-detection by field name
    if "maxicode" in name_lower:
        if "^BD" in zpl_commands or any(b["type"] == "MAXICODE" for b in barcodes):
            return True, "MaxiCode present"

    if "service_icon" in name_lower or "graphic" in name_lower:
        if graphics:
            return True, f"{len(graphics)} graphic(s)"

    if "postal_barcode" in name_lower:
        for bc in barcodes:
            if bc["data"].startswith("420") or bc["data"].startswith("421"):
                return True, bc["data"][:30]

    if "pdf417" in name_lower:
        if "^B7" in zpl_commands:
            return True, "PDF417 present"

    # Text prefix auto-detection
    prefix_map = {
        "billing": "BILLING:", "description": "DESC:", "goods": "DESC:",
        "tracking": "TRACKING #:", "shp_number": "SHP#:",
        "shipment_number": "SHP#:", "shipment_date": "DATE:",
        "date": "DATE:", "shipment_weight": "SHP WT:",
    }
    for keyword, prefix in prefix_map.items():
        if keyword in name_lower:
            for t in texts:
                if t.upper().strip().startswith(prefix):
                    return True, t.strip()[:50]

    # Description-based auto-detection
    if "international" in desc_lower and "notice" in desc_lower:
        for t in texts:
            if "shipper agrees" in t.lower():
                return True, t[:50]

    if "routing code" in desc_lower and "version" not in desc_lower:
        for t in texts:
            if re.match(r"^[A-Z]{2,3}\s+\d{3}\s+\d-\d{2}$", t.strip()):
                return True, t.strip()

    if "service title" in desc_lower or "service_title" in name_lower:
        for t in texts:
            upper = t.upper().strip()
            if any(upper.startswith(p) for p in ["UPS ", "DHL ", "FEDEX ", "TNT "]):
                return True, upper

    if "package count" in desc_lower or "package_count" in name_lower or "piece_count" in name_lower:
        for t in texts:
            if re.search(r"\d+\s+OF\s+(\d+|_)", t, re.IGNORECASE):
                return True, t.strip()

    if "country" in name_lower:
        country_names = {
            "GERMANY", "FRANCE", "SPAIN", "PORTUGAL", "ITALY", "NETHERLANDS",
            "BELGIUM", "AUSTRIA", "SWITZERLAND", "SWEDEN", "UNITED KINGDOM",
            "POLAND", "DENMARK", "NORWAY", "FINLAND", "IRELAND", "HUNGARY",
            "ROMANIA", "GREECE", "CZECH REPUBLIC", "USA", "CANADA", "BRAZIL",
            "MEXICO", "JAPAN", "CHINA", "INDIA", "AUSTRALIA", "SINGAPORE",
        }
        for t in texts:
            if t.upper().strip() in country_names:
                return True, t.strip()

    # Weight auto-detection
    if "weight" in name_lower and "dim" not in name_lower:
        for t in texts:
            if re.match(r"^\d+(\.\d+)?\s+(KG|LBS?)\s*$", t.strip(), re.IGNORECASE):
                if "SHP" not in t.upper():
                    return True, t.strip()

    return False, "Not found"


def _find_ship_to_y(text_blocks: list) -> Optional[float]:
    """Find the Y position of the SHIP TO marker."""
    for block in text_blocks:
        text = block["text"].upper().strip()
        if text in ("SHIP", "SHIP TO:", "SHIP TO"):
            return block["y"]
    return None


# ═══════════════════════════════════════════════════════════════
# LABEL VALIDATOR CLASS
# ═══════════════════════════════════════════════════════════════

class LabelValidator:
    def __init__(self, rules: Dict[str, Any], carrier_name: str = ""):
        self.rules = rules
        self.carrier_name = carrier_name

    async def validate(self, label_data: bytes, is_zpl: bool = False) -> Dict[str, Any]:
        errors: List[ValidationError] = []
        parsed_data = {}
        original_script = ""
        barcodes = []
        layout_blocks = []
        raw_data = None

        if is_zpl:
            original_script = label_data if isinstance(label_data, str) else label_data.decode("utf-8")
            from app.services.zpl_parser import parse_zpl_to_raw, parse_zpl_script

            # New: get raw data for detect_by matching
            raw_data = parse_zpl_to_raw(original_script)
            # Backward compat: also get parsed data for legacy field matching
            parsed_data = parse_zpl_script(original_script)
        # Debug: print everything the parser extracted
        if raw_data:
            print("\n" + "=" * 60)
            print("ZPL PARSER RAW OUTPUT")
            print("=" * 60)
            print(f"  Text blocks: {len(raw_data.get('text_blocks', []))}")
            for b in raw_data.get("text_blocks", []):
                print(f"    ({b['x']:>5.0f}, {b['y']:>5.0f}) font={b['font_size']:>2d}  {b['text'][:70]!r}")
            print(f"\n  Barcodes: {len(raw_data.get('barcodes', []))}")
            for b in raw_data.get("barcodes", []):
                print(f"    {b['type']:15s} h={b['height']:>3d}  {b['data'][:50]!r}")
            print(f"\n  Graphics: {len(raw_data.get('graphics', []))}")
            for g in raw_data.get("graphics", []):
                print(f"    {g['type']}  ({g['x']:.0f},{g['y']:.0f})  {g['total_bytes']} bytes")
            print(f"\n  ZPL commands: {raw_data.get('zpl_commands', [])}")
            print("=" * 60 + "\n")
        else:
            img = self._load_image(label_data)
            if img is None:
                return self._fail_response("Unreadable image file.")
            text_content = self._extract_text(img)
            parsed_data = self._parse_ocr_text(text_content)
            barcodes = self.detect_barcodes(img)
            layout_blocks = self.detect_layout_blocks(img)

        # Primary: detect_by validation (for ZPL labels with raw_data)
        # Falls back to legacy field matching if detect_by is not available
        field_errors, field_score, field_total = await self._validate_fields(
            parsed_data, raw_data, original_script
        )

        barcode_errors, barcode_score, barcode_total = await self._validate_barcode(
            barcodes, parsed_data
        )
        layout_errors, layout_score, layout_total = self._validate_layout(layout_blocks)

        errors.extend(field_errors)
        errors.extend(barcode_errors)
        errors.extend(layout_errors)

        total_possible = field_total + barcode_total + layout_total
        total_earned = field_score + barcode_score + layout_score
        compliance_score = round(total_earned / total_possible, 2) if total_possible > 0 else 0.0

        status = "PASS" if not errors else "FAIL"

        corrected_script = None
        if is_zpl and errors:
            corrected_script = self._auto_correct_zpl(original_script, parsed_data, errors)

        return {
            "status": status,
            "errors": [e.dict() for e in errors],
            "corrected_label_script": corrected_script,
            "compliance_score": compliance_score
        }

    async def _validate_fields(self, parsed_data: dict,
                                raw_data: dict = None,
                                original_script: str = ""):
        errors = []
        earned = 0.0
        total = 0.0

        db = _get_db()

        field_formats = {
            k: v for k, v in self.rules.get("field_formats", {}).items()
            if k != "barcode"
        }

        # Merge mandatory overrides from MongoDB
        overrides = await _load_mandatory_overrides(db, self.carrier_name)
        for field_name, override in overrides.items():
            if field_name not in field_formats:
                field_formats[field_name] = override
                print(f"  [Learned] Added mandatory check: '{field_name}'")
            elif not field_formats[field_name].get("required", False):
                field_formats[field_name]["required"] = True
                print(f"  [Learned] Made '{field_name}' required (was optional)")

        for field_name, rule in field_formats.items():
            weight = 0.1
            total += weight
            required = rule.get("required", False)
            detect_by = rule.get("detect_by", "")
            pattern = rule.get("pattern", "")
            description = rule.get("description", "")

            found = False
            actual_value = "Not found"

            # ══════════════════════════════════════════════════
            # PRIMARY: detect_by matching against raw ZPL data
            # This is the main validation path for ZPL labels
            # ══════════════════════════════════════════════════
            if raw_data and (detect_by or not pattern):
                found, actual_value = _detect_field_by_rule(
                    raw_data, detect_by, field_name, description
                )

            # ══════════════════════════════════════════════════
            # FALLBACK: legacy field name matching
            # Used when detect_by is empty and pattern exists,
            # or for image-based (non-ZPL) validation
            # ══════════════════════════════════════════════════
            if not found and not raw_data:
                value = parsed_data.get(field_name)
                if value and pattern:
                    try:
                        if re.match(pattern, str(value)):
                            found = True
                            actual_value = str(value)
                    except re.error:
                        found = bool(value)
                        actual_value = str(value)
                elif value:
                    found = True
                    actual_value = str(value)

            # Also try legacy matching even with raw_data as second chance
            # Also try legacy matching even with raw_data as second chance
            if not found and raw_data and parsed_data:
                value = parsed_data.get(field_name)
                if value:
                    found = True
                    actual_value = str(value)

            print(f"  [Validate] {field_name:30s} | required={required} | detect_by='{detect_by}' | pattern='{pattern[:30] if pattern else ''}' | found={found} | actual={actual_value[:40] if actual_value else 'N/A'}")
            if found:
                earned += weight
            elif required:
                # Check if user flagged this as wrong before
                if check_corrections_before_failing(
                    db, self.carrier_name, field_name
                ):
                    earned += weight
                    continue

                errors.append(ValidationError(
                    field=field_name,
                    expected="Required field",
                    actual=actual_value,
                    description=f"{field_name} not found on label. {description}"
                ))

        return errors, earned, total

    async def _validate_barcode(self, barcodes, parsed_data):
        errors = []
        earned = 0.0
        total = 0.1

        barcode_rule = self.rules.get("field_formats", {}).get("barcode", {})
        required = barcode_rule.get("required", False)

        zpl_barcode = parsed_data.get("barcode")
        value = zpl_barcode if zpl_barcode else (
            barcodes[0]["data"] if barcodes else None
        )

        if value:
            earned += 0.1
        elif required:
            db = _get_db()
            if check_corrections_before_failing(
                db, self.carrier_name, "barcode"
            ):
                earned += 0.1
            else:
                errors.append(ValidationError(
                    field="barcode",
                    expected="At least one barcode",
                    actual="Not found",
                    description="Barcode validation failed."
                ))
        else:
            earned += 0.1

        return errors, earned, total

    def _validate_layout(self, layout_blocks):
        errors = []
        earned = 0.0
        total = 0.05

        layout_rules = self.rules.get("layout_constraints", {})
        min_blocks = layout_rules.get("min_blocks", 0)

        if min_blocks and len(layout_blocks) < min_blocks:
            errors.append(ValidationError(
                field="layout",
                expected=f"At least {min_blocks} layout blocks",
                actual=f"{len(layout_blocks)} detected",
                description="Label layout incomplete."
            ))
        else:
            earned += 0.05

        return errors, earned, total

    def _load_image(self, image_data: bytes):
        nparr = np.frombuffer(image_data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def _extract_text(self, img) -> str:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        return pytesseract.image_to_string(gray)

    def _parse_ocr_text(self, text: str) -> Dict[str, str]:
        parsed = {}
        tracking_match = re.search(r"\b\d{10,22}\b", text)
        if tracking_match:
            parsed["tracking_number"] = tracking_match.group()
        postal_match = re.search(r"\b\d{5}(-\d{4})?\b", text)
        if postal_match:
            parsed["postal_code"] = postal_match.group()
        weight_match = re.search(
            r"\b\d+(\.\d+)?\s?(KG|LB|kg|lb)\b", text, re.IGNORECASE
        )
        if weight_match:
            parsed["weight"] = weight_match.group()
        country_match = re.search(r"\b[A-Z]{2}\b", text)
        if country_match:
            parsed["country_code"] = country_match.group()
        return parsed

    def detect_barcodes(self, img) -> list:
        if pyzbar is None:
            return []
        try:
            decoded = pyzbar.decode(img)
            return [
                {"data": d.data.decode("utf-8"), "type": d.type}
                for d in decoded
            ]
        except Exception:
            return []

    def detect_layout_blocks(self, img) -> list:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            blocks = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                if w > 30 and h > 15:
                    blocks.append({"x": x, "y": y, "w": w, "h": h})
            return blocks
        except Exception:
            return []

    def _auto_correct_zpl(self, original_script: str, parsed_data: dict,
                          errors: list) -> str:
        corrected = original_script.strip()
        comments = []
        for error in errors:
            field = (error.field if hasattr(error, 'field')
                     else error.get('field', ''))
            expected = (error.expected if hasattr(error, 'expected')
                        else error.get('expected', ''))
            actual = (error.actual if hasattr(error, 'actual')
                      else error.get('actual', ''))
            if actual == "Not found":
                comments.append(
                    f"^FX WARNING: Missing field '{field}'. Expected: {expected}"
                )
            else:
                comments.append(
                    f"^FX WARNING: Field '{field}' has value '{actual}' "
                    f"but expected: {expected}"
                )
        if comments:
            comment_block = "\n".join(comments)
            corrected = corrected.replace(
                "^XZ", f"\n{comment_block}\n^XZ"
            )
        return corrected

    def _fail_response(self, message):
        return {
            "status": "FAIL",
            "errors": [{
                "field": "file", "expected": "Valid image",
                "actual": "Unreadable file", "description": message
            }],
            "corrected_label_script": None,
            "compliance_score": 0.0
        }