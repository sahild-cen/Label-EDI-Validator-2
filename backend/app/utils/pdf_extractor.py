import pdfplumber
from typing import Dict, Any, Tuple
import re


def extract_structured_pdf_data(pdf_path):
    raw_text = ""
    text_blocks = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            raw_text += page_text + "\n"

            words = page.extract_words()
            for word in words:
                text_blocks.append({
                    "text": word["text"],
                    "bbox": [word["x0"], word["top"], word["x1"], word["bottom"]]
                })

    is_text_based = len(raw_text.strip()) > 50

    return {
        "raw_text": raw_text,
        "text_blocks": text_blocks,
        "metadata": {"is_text_based": is_text_based}
    }


def generate_rule_template_from_spec(spec_data, spec_type):

    raw_text = spec_data.get("raw_text", "")
    text_blocks = spec_data.get("text_blocks", [])
    raw_text_upper = raw_text.upper()

    rules = {
        "required_fields": [],
        "field_formats": {},
        "layout_constraints": {},
        "validation_patterns": {}
    }

    field_score = 0
    pattern_score = 0
    layout_score = 0

    # ---------------------------------------------------
    # LABEL SPEC PROCESSING
    # ---------------------------------------------------
    if spec_type == "label":

        # ── Tracking Number ──
        tracking_regex = re.search(
            r"tracking\s*number.*?(\d{1,2})\s*[-to]{0,3}\s*(\d{1,2})?\s*(alphanumeric|numeric)?",
            raw_text, re.IGNORECASE
        )
        if tracking_regex:
            min_len = tracking_regex.group(1)
            max_len = tracking_regex.group(2) or min_len
            # Ensure min <= max
            min_int = int(min_len)
            max_int = int(max_len)
            if min_int > max_int:
                min_int, max_int = max_int, min_int
            pattern = "^[A-Z0-9]{" + str(min_int) + "," + str(max_int) + "}$"
            rules["field_formats"]["tracking_number"] = {
                "pattern": pattern,
                "required": True
            }
            rules["required_fields"].append("tracking_number")
            field_score += 1
            pattern_score += 1

        # ── Shipment Number ──
        shipment_regex = re.search(
            r"(?:shipment|consignment|airwaybill|awb)\s*(?:number|id|identifier).*?(\d{1,2})\s*[-to]{0,3}\s*(\d{1,2})?",
            raw_text, re.IGNORECASE
        )
        if shipment_regex:
            min_len = shipment_regex.group(1)
            max_len = shipment_regex.group(2) or min_len
            min_int = int(min_len)
            max_int = int(max_len)
            if min_int > max_int:
                min_int, max_int = max_int, min_int
            pattern = "^[A-Z0-9]{" + str(min_int) + "," + str(max_int) + "}$"
            rules["field_formats"]["shipment_number"] = {
                "pattern": pattern,
                "required": False  # Conditional per DHL spec (not mandatory for all products)
            }
            rules["required_fields"].append("shipment_number")
            field_score += 1
            pattern_score += 1

        # ── Barcode ──
        barcode_types = [
            "CODE128", "CODE 128", "QR", "PDF417", "DATAMATRIX",
            "DATA MATRIX", "EAN128", "EAN-128", "GS1-128",
            "INTERLEAVED", "ITF", "CODE39"
        ]
        for barcode in barcode_types:
            if barcode in raw_text_upper:
                normalized = barcode.replace(" ", "").replace("-", "")
                rules["field_formats"]["barcode"] = {
                    "format": normalized,
                    "required": True
                }
                rules["required_fields"].append("barcode")
                field_score += 1
                pattern_score += 1
                break

        # ── Postal Code ──
        # When spec mentions multiple country formats, use a GENERIC pattern
        # that accepts any alphanumeric postal code (3-10 chars)
        if "POSTAL" in raw_text_upper or "ZIP" in raw_text_upper or "POSTCODE" in raw_text_upper:
            # Check if spec mentions multiple countries / variable formats
            multi_country = bool(re.search(
                r"(?:country|varies|variable|local standards|NL|PL|GB|SE|US|DE|FR)",
                raw_text, re.IGNORECASE
            ))

            if multi_country:
                # Generic pattern — postal codes vary by country
                postal_pattern = "^[A-Z0-9\\s-]{3,10}$"
            else:
                # Try to detect specific single-country format
                if re.search(r"[A-Z]\d[A-Z]\s?\d[A-Z]\d", raw_text):
                    postal_pattern = "^[A-Z]\\d[A-Z]\\s?\\d[A-Z]\\d$"  # Canada
                elif re.search(r"[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2}", raw_text):
                    postal_pattern = "^[A-Z]{1,2}\\d{1,2}\\s?\\d[A-Z]{2}$"  # UK
                else:
                    postal_pattern = "^[A-Z0-9\\s-]{3,10}$"  # Generic fallback

            rules["field_formats"]["postal_code"] = {
                "pattern": postal_pattern,
                "required": False  # Optional per DHL spec section 5.5.2
            }
            field_score += 1
            pattern_score += 1

        # ── Weight ──
        if re.search(r"(?:weight|gross\s*weight|actual\s*weight)", raw_text, re.IGNORECASE):
            rules["field_formats"]["weight"] = {
                "pattern": "^\\d+(\\.\\d+)?\\s?(KG|LB|kg|lb|G|g)$",
                "required": False
            }
            field_score += 1

        # ── Country Code ──
        if re.search(r"(?:country\s*code|destination\s*country|iso\s*3166)", raw_text, re.IGNORECASE):
            rules["field_formats"]["country_code"] = {
                "pattern": "^[A-Z]{2}$",
                "required": False  # Not always on label; sometimes in address
            }
            field_score += 1

        # ── Service Type ──
        if re.search(r"(?:service\s*(?:type|code|indicator)|product\s*(?:code|type|name))", raw_text, re.IGNORECASE):
            rules["field_formats"]["service_type"] = {
                "pattern": "",  # Varies too much between carriers
                "required": True,
                "description": "Product/service name on label"
            }
            rules["required_fields"].append("service_type")
            field_score += 1

        # ── License Plate ──
        if re.search(r"license\s*plate|licence\s*plate|SSCC", raw_text, re.IGNORECASE):
            rules["field_formats"]["license_plate"] = {
                "pattern": "^[A-Z0-9]{10,35}$",
                "required": True,
                "description": "Unique piece identifier per ISO 15459"
            }
            rules["required_fields"].append("license_plate")
            field_score += 1
            pattern_score += 1

        # ── Layout Size ──
        size_match = re.search(r"(\d+)\s*[xX]\s*(\d+)\s*(mm|cm|inch|in)?", raw_text)
        if size_match:
            w = int(size_match.group(1))
            h = int(size_match.group(2))
            unit = size_match.group(3) or "mm"
            rules["layout_constraints"] = {
                "label_width": w,
                "label_height": h,
                "units": unit
            }
            layout_score += 1

        if len(text_blocks) > 20:
            layout_score += 0.5

        # Confidence
        field_conf = min(field_score / 5, 1.0)
        pattern_conf = min(pattern_score / 5, 1.0)
        layout_conf = min(layout_score / 1.5, 1.0)
        confidence_score = round(0.4 * field_conf + 0.4 * pattern_conf + 0.2 * layout_conf, 2)

    # ---------------------------------------------------
    # EDI SPEC PROCESSING
    # ---------------------------------------------------
    elif spec_type == "edi":
        rules["required_segments"] = []
        standard_x12 = ["ISA", "GS", "ST", "SE", "GE", "IEA"]
        edifact_segs = ["UNB", "UNH", "UNT", "UNZ", "BGM", "DTM"]

        for seg in standard_x12:
            if seg in raw_text_upper:
                rules["required_segments"].append(seg)

        for seg in edifact_segs:
            if seg in raw_text_upper and seg not in rules["required_segments"]:
                rules["required_segments"].append(seg)

        if any(s in rules["required_segments"] for s in ["ISA", "GS", "ST"]):
            rules["format_type"] = "x12"
            rules["delimiter_rules"] = {
                "segment_delimiter": "~",
                "element_delimiter": "*",
                "sub_element_delimiter": ":"
            }
        elif any(s in rules["required_segments"] for s in ["UNB", "UNH"]):
            rules["format_type"] = "edifact"
            rules["delimiter_rules"] = {
                "segment_delimiter": "'",
                "element_delimiter": "+",
                "sub_element_delimiter": ":"
            }

        rules["segment_order"] = rules["required_segments"] or standard_x12

        rules["required_fields"] = []
        edi_fields = [
            "sender_id", "receiver_id", "interchange_control",
            "transaction_set", "purchase_order", "invoice_number"
        ]
        for field in edi_fields:
            if field.replace("_", " ").upper() in raw_text_upper:
                rules["required_fields"].append(field)

        all_segments = standard_x12 + edifact_segs
        confidence_score = round(
            min(len(rules["required_segments"]) / max(len(all_segments) / 2, 1), 1.0), 2
        )

    else:
        confidence_score = 0.0

    return rules, confidence_score