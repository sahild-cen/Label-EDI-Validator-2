import cv2
import numpy as np
from typing import Dict, Any


def detect_layout_blocks(image_bytes: bytes) -> Dict[str, Any]:
    """
    Detect major layout regions in brochure-style label PDFs.
    Returns bounding boxes for detected regions.
    """

    # Convert bytes to OpenCV image
    np_arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image is None:
        return {}

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Edge detection
    edges = cv2.Canny(gray, 50, 150)

    # Find contours (possible blocks)
    contours, _ = cv2.findContours(
        edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    detected_blocks = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)

        # Filter very small boxes (noise removal)
        if w > 50 and h > 30:
            detected_blocks.append({
                "x": x,
                "y": y,
                "width": w,
                "height": h
            })

    return {
        "detected_blocks": detected_blocks,
        "block_count": len(detected_blocks)
    }


def run_layout_fallback(image_bytes: bytes) -> Dict[str, Any]:
    """
    Main fallback entrypoint.
    """

    layout_info = detect_layout_blocks(image_bytes)

    # Simple heuristic rule generation
    rules = {}

    if layout_info.get("block_count", 0) >= 3:
        rules["layout_constraints"] = {
            "min_blocks_detected": layout_info["block_count"]
        }

    return rules
