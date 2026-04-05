import re
import cv2
import numpy as np
import pytesseract
from typing import Dict, Any, List, Optional
from app.models.validation import ValidationError
from app.routes.corrections import check_corrections_before_failing


try:
    from pyzbar import pyzbar
except Exception:
    pyzbar = None


# ═══════════════════════════════════════════════════════════════
# FIELD NAME ALIASING — same as your existing code
# ═══════════════════════════════════════════════════════════════

FIELD_ALIASES = {
    "tracking_number": [
        "tracking_number", "shipment_number", "waybill_number",
        "consignment_number", "tracking_id",
    ],
    "postal_code": [
        "postal_code", "ship_to_postal_code", "postcode",
        "zip_code", "destination_postal_code", "receiver_postal_code",
        "destination_zip",
    ],
    "city": [
        "city", "ship_to_city", "destination_city", "receiver_city", "town",
    ],
    "country_code": [
        "country_code", "destination_country", "ship_to_country",
        "receiver_country",
    ],
    "weight": [
        "weight", "package_weight", "gross_weight", "shipment_weight",
        "actual_weight",
    ],
    "service_type": [
        "service_type", "service_title", "service_name", "service_code",
        "product", "product_type", "delivery_service", "service_description",
    ],
    "service_title": [
        "service_type", "service_title", "service_name", "service_description",
    ],
    "service_description": [
        "service_description", "service_type", "service_title", "service_name",
        "product", "product_type", "delivery_service",
    ],
    "sender_address": [
        "sender_address", "ship_from_address", "shipper_address",
        "from_address", "origin_address",
    ],
    "receiver_address": [
        "receiver_address", "ship_to_address", "recipient_address",
        "to_address", "destination_address", "consignee_address",
    ],
    "sender_name": [
        "sender_name", "shipper_name", "from_name", "ship_from_name",
    ],
    "receiver_name": [
        "receiver_name", "recipient_name", "to_name", "ship_to_name",
        "consignee_name",
    ],
    "piece_count": [
        "piece_count", "package_count", "pieces", "number_of_pieces",
    ],
    "reference_number": [
        "reference_number", "reference", "customer_reference", "ref_number",
    ],
    "billing": [
        "billing", "billing_method", "billing_type", "payment_method",
    ],
    "billing_method": [
        "billing", "billing_method", "billing_type", "payment_method",
    ],
    "license_plate": [
        "license_plate", "licence_plate", "sscc", "sscc_barcode",
    ],
    "routing_barcode": [
        "routing_barcode", "routing_code", "sort_code", "ups_routing_code",
        "ursa_routing_code",
    ],
    "routing_code": [
        "routing_code", "routing_barcode", "sort_code", "ups_routing_code",
        "ursa_routing_code", "ursa_code",
    ],
    "barcode": [
        "barcode", "tracking_number", "tracking_barcode",
    ],
    "goods_description": [
        "goods_description", "description", "desc", "content",
    ],
    "shipment_date": [
        "shipment_date", "ship_date", "date", "pickup_date",
        "dispatch_date", "collection_date",
    ],
    "destination_airport": [
        "destination_airport", "airport_id", "airport_code", "dest_airport",
    ],
    "special_handling": [
        "special_handling", "special_handling_codes", "handling_codes",
    ],
    "form_id": [
        "form_id", "form_code", "form_number",
    ],
    "bill_type": [
        "bill_type", "billing", "billing_method", "billing_type",
    ],
}

# Regex sanity checks — same as your existing code
REGEX_SANITY = {
    "tracking_number": {
        "check": lambda r: _max_length_below(r, 15),
        "fix": None,
        "message": "Tracking number regex too restrictive, skipping pattern check",
    },
    "postal_code": {
        "check": lambda r: r in (r"^[A-Za-z0-9]{5}$", r"^\d{5}$", r"^.{5}$"),
        "fix": None,
        "message": "Postal code regex too restrictive for international use",
    },
    "city": {
        "check": lambda r: _max_length_below(r, 30),
        "fix": None,
        "message": "City regex too restrictive",
    },
}


def _max_length_below(regex: str, threshold: int) -> bool:
    quants = re.findall(r"\{(\d+),(\d+)\}", regex)
    for _, max_v in quants:
        if int(max_v) < threshold:
            return True
    single = re.findall(r"(?<!\{)\{(\d+)\}(?!,)", regex)
    for val in single:
        if int(val) < threshold:
            return True
    return False


def _find_parsed_value(parsed_data: dict, field_name: str) -> Optional[str]:
    val = parsed_data.get(field_name)
    if val:
        return str(val)

    aliases = FIELD_ALIASES.get(field_name, [])
    for alias in aliases:
        val = parsed_data.get(alias)
        if val:
            return str(val)

    for canonical, alias_list in FIELD_ALIASES.items():
        if field_name in alias_list:
            val = parsed_data.get(canonical)
            if val:
                return str(val)
            for alias in alias_list:
                val = parsed_data.get(alias)
                if val:
                    return str(val)

    return None


def _get_db():
    try:
        from app.database import get_database
        return get_database()
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# NEW: Load mandatory field overrides from MongoDB
# ═══════════════════════════════════════════════════════════════
# When users report "you missed this check", it gets stored in
# mandatory_field_overrides. We load them here and merge into
# the extracted rules so they get validated.
#
# This is NOT hardcoded — it's entirely driven by user feedback
# stored in MongoDB. Works for any carrier, any field.

def _load_mandatory_overrides(db, carrier_name: str) -> dict:
    """Load user-reported mandatory fields from MongoDB."""
    if db is None:
        return {}
    try:
        overrides = {}
        for doc in db.mandatory_field_overrides.find({
            "carrier": carrier_name.lower().strip(),
            "required": True,
        }):
            overrides[doc["field"]] = {
                "required": True,
                "pattern": doc.get("pattern"),
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
# LABEL VALIDATOR — your existing class with 2 additions
# ═══════════════════════════════════════════════════════════════

class LabelValidator:
    def __init__(self, rules: Dict[str, Any], carrier_name: str = ""):
        self.rules = rules
        self.carrier_name = carrier_name  # ADDITION 1: pass carrier name

    async def validate(self, label_data: bytes, is_zpl: bool = False) -> Dict[str, Any]:
        errors: List[ValidationError] = []
        parsed_data = {}
        original_script = ""
        barcodes = []
        layout_blocks = []

        if is_zpl:
            original_script = label_data.decode("utf-8")
            from app.services.zpl_parser import parse_zpl_script
            parsed_data = parse_zpl_script(original_script)
        else:
            img = self._load_image(label_data)
            if img is None:
                return self._fail_response("Unreadable image file.")
            text_content = self._extract_text(img)
            parsed_data = self._parse_ocr_text(text_content)
            barcodes = self.detect_barcodes(img)
            layout_blocks = self.detect_layout_blocks(img)

        field_errors, field_score, field_total = self._validate_fields(parsed_data)
        barcode_errors, barcode_score, barcode_total = self._validate_barcode(barcodes, parsed_data)
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
        weight_match = re.search(r"\b\d+(\.\d+)?\s?(KG|LB|kg|lb)\b", text, re.IGNORECASE)
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
            return [{"data": d.data.decode("utf-8"), "type": d.type} for d in decoded]
        except Exception:
            return []

    def detect_layout_blocks(self, img) -> list:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            blocks = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                if w > 30 and h > 15:
                    blocks.append({"x": x, "y": y, "w": w, "h": h})
            return blocks
        except Exception:
            return []

    def _validate_fields(self, parsed_data: dict):
        errors = []
        earned = 0.0
        total = 0.0

        db = _get_db()

        field_formats = {
            k: v for k, v in self.rules.get("field_formats", {}).items()
            if k != "barcode"
        }

        # ══════════════════════════════════════════════════════
        # ADDITION 2: Merge mandatory overrides from MongoDB
        # These come from user feedback ("you missed this check")
        # ══════════════════════════════════════════════════════
        overrides = _load_mandatory_overrides(db, self.carrier_name)
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
            pattern = rule.get("pattern")

            value = _find_parsed_value(parsed_data, field_name)

            passed = False

            if value and pattern:
                sanity = REGEX_SANITY.get(field_name)
                if sanity and sanity["check"](pattern):
                    print(f"  [Validator] {field_name}: {sanity['message']} ('{pattern}')")
                    passed = True
                else:
                    try:
                        if re.match(pattern, str(value)):
                            passed = True
                    except re.error:
                        passed = bool(value)
            elif value and not pattern:
                passed = True

            if passed:
                earned += weight
            elif required:
                # ══════════════════════════════════════════════
                # ADDITION 3: Check if user said this error is wrong
                # If so, suppress it — don't report it again
                # ══════════════════════════════════════════════
                if check_corrections_before_failing(db, self.carrier_name, field_name):
                    earned += weight
                    continue

                if not value:
                    actual_msg = "Not found"
                    desc = f"{field_name} not found on label."
                else:
                    actual_msg = str(value)
                    desc = f"{field_name} validation failed."

                errors.append(ValidationError(
                    field=field_name,
                    expected=f"Pattern: {pattern}" if pattern else "Required field",
                    actual=actual_msg,
                    description=desc
                ))

        return errors, earned, total

    def _validate_barcode(self, barcodes, parsed_data):
        errors = []
        earned = 0.0
        total = 0.1

        barcode_rule = self.rules.get("field_formats", {}).get("barcode", {})
        required = barcode_rule.get("required", False)
        pattern = barcode_rule.get("pattern")

        zpl_barcode = parsed_data.get("barcode")
        value = zpl_barcode if zpl_barcode else (barcodes[0]["data"] if barcodes else None)

        passed = False
        if value:
            if pattern:
                try:
                    passed = bool(re.match(pattern, value))
                except re.error:
                    passed = True
            else:
                passed = True

        if required and not passed:
            db = _get_db()
            if check_corrections_before_failing(db, self.carrier_name, "barcode"):
                earned += 0.1
            else:
                errors.append(ValidationError(
                    field="barcode",
                    expected=f"Pattern: {pattern}" if pattern else "At least one barcode",
                    actual=value if value else "Not found",
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

    def _auto_correct_zpl(self, original_script: str, parsed_data: dict,
                          errors: list) -> str:
        corrected = original_script.strip()
        comments = []
        for error in errors:
            field = error.field if hasattr(error, 'field') else error.get('field', '')
            expected = error.expected if hasattr(error, 'expected') else error.get('expected', '')
            actual = error.actual if hasattr(error, 'actual') else error.get('actual', '')
            if actual == "Not found":
                comments.append(f"^FX WARNING: Missing field '{field}'. Expected: {expected}")
            else:
                comments.append(f"^FX WARNING: Field '{field}' has value '{actual}' but expected: {expected}")
        if comments:
            comment_block = "\n".join(comments)
            corrected = corrected.replace("^XZ", f"\n{comment_block}\n^XZ")
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