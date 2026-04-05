import cv2
import numpy as np
from typing import List, Dict


def detect_arrows(image_bytes: bytes) -> List[Dict]:
    """
    Detect arrow-like line structures.
    """

    np_arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image is None:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)

    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=50,
        minLineLength=50,
        maxLineGap=10
    )

    arrows = []

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]

            length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

            if length > 60:
                arrows.append({
                    "start": (x1, y1),
                    "end": (x2, y2),
                    "length": length
                })

    return arrows
