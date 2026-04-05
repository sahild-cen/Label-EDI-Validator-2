import fitz  # PyMuPDF
import re
from typing import List, Dict


def extract_text_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks, breaking at sentence boundaries."""
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at a sentence boundary
        if end < len(text):
            boundary = text.rfind(".", start + chunk_size - 300, end)
            if boundary > start:
                end = boundary + 1

        chunks.append(text[start:end].strip())
        start += chunk_size - overlap

    return [c for c in chunks if len(c) > 20]


def detect_sections(text: str) -> List[Dict]:
    """
    Detect section headings in carrier specification documents.
    Supports:
      - Numbered: 3 Label Layout, 4.1 Barcode Requirements
      - ALL CAPS: BARCODE REQUIREMENTS
    """
    lines = text.split("\n")
    sections = []
    current_section = {"title": "intro", "content": []}

    heading_pattern = re.compile(
        r'^(\d+(\.\d+)*)\s+[A-Z][A-Za-z\s\-\/\(\)&]+$'
    )
    caps_heading = re.compile(r'^[A-Z][A-Z\s\-\/\(\)&]{5,}$')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        is_heading = heading_pattern.match(line) or (
            caps_heading.match(line) and len(line) < 60
        )

        if is_heading:
            if current_section["content"] or current_section["title"] != "intro":
                sections.append(current_section)
            current_section = {"title": line, "content": []}
        else:
            current_section["content"].append(line)

    if current_section["content"]:
        sections.append(current_section)

    return sections


RULE_SECTION_KEYWORDS = [
    "label", "barcode", "routing", "field", "data", "format",
    "code", "shipment", "address", "tracking", "license plate",
    "dimension", "weight", "postal", "service", "encoding",
    "mandatory", "required", "element", "segment", "edi",
    "specification", "validation", "structure"
]


def filter_rule_sections(sections: List[Dict]) -> List[Dict]:
    """Keep only sections whose titles suggest they contain rules."""
    filtered = []

    for section in sections:
        title = section["title"].lower()

        if any(keyword in title for keyword in RULE_SECTION_KEYWORDS):
            filtered.append(section)
            continue

        # Also check first few lines of content
        preview = " ".join(section["content"][:5]).lower()
        if any(keyword in preview for keyword in RULE_SECTION_KEYWORDS[:10]):
            filtered.append(section)

    # If nothing matched, return all (don't lose data)
    return filtered if filtered else sections