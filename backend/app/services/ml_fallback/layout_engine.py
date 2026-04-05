from typing import Dict, Any
import math

from app.services.ml_fallback.layout_detector import detect_layout_blocks
from app.services.ml_fallback.arrow_detector import detect_arrows
from app.services.ml_fallback.ocr_engine import extract_text_blocks_from_image


def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def find_nearest_text(arrow_tip, text_blocks):
    """
    Find OCR text closest to arrow tip.
    """
    min_dist = float("inf")
    closest_text = None

    for block in text_blocks:
        x0, y0, x1, y1 = block["bbox"]
        center = ((x0 + x1) // 2, (y0 + y1) // 2)

        d = distance(arrow_tip, center)

        if d < min_dist:
            min_dist = d
            closest_text = block["text"]

    return closest_text


def run_layout_fallback(image_bytes: bytes) -> (Dict[str, Any], float):

    rules = {
        "required_fields": [],
        "layout_constraints": {}
    }

    layout_info = detect_layout_blocks(image_bytes)
    arrows = detect_arrows(image_bytes)
    text_blocks = extract_text_blocks_from_image(image_bytes)

    annotated_fields = {}
    field_hits = 0

    for arrow in arrows:
        tip = arrow["end"]
        nearest_text = find_nearest_text(tip, text_blocks)

        if nearest_text:
            field_name = nearest_text.lower()

            if "tracking" in field_name:
                rules["required_fields"].append("tracking_number")
                annotated_fields["tracking_number"] = {"arrow_tip": tip}
                field_hits += 1

            elif "barcode" in field_name:
                rules["required_fields"].append("barcode")
                annotated_fields["barcode"] = {"arrow_tip": tip}
                field_hits += 1

            elif "postal" in field_name or "zip" in field_name:
                rules["required_fields"].append("postal_code")
                annotated_fields["postal_code"] = {"arrow_tip": tip}
                field_hits += 1

    if annotated_fields:
        rules["layout_constraints"]["annotated_fields"] = annotated_fields

    # ML confidence calculation
    max_possible = 3
    field_conf = field_hits / max_possible
    arrow_conf = min(len(arrows) / 3, 1.0)
    block_conf = min(layout_info.get("block_count", 0) / 5, 1.0)

    ml_confidence = (
        0.5 * field_conf +
        0.3 * arrow_conf +
        0.2 * block_conf
    )

    ml_confidence = round(min(ml_confidence, 1.0), 2)

    return rules, ml_confidence
