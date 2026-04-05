import pytesseract
import cv2
import numpy as np
from typing import List, Dict


def extract_text_blocks_from_image(image_bytes: bytes) -> List[Dict]:
    """
    Extract word-level OCR data with bounding boxes.
    """

    np_arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image is None:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]

    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

    text_blocks = []

    for i in range(len(data["text"])):
        text = data["text"][i].strip()

        if text:
            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]

            text_blocks.append({
                "text": text,
                "bbox": [x, y, x + w, y + h]
            })

    return text_blocks
