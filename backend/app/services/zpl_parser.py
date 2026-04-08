"""
ZPL Raw Data Extractor
=======================
Extracts ALL data from a ZPL script into a structured format
that the validator can match against rules.

This parser makes ZERO assumptions about what each field "is".
It just extracts:
  - Every text block (^FD) with its position
  - Every barcode command and its data
  - Every graphic element
  - Every ZPL command present

The validator then uses the "detect_by" field from the rules
to find each required element in this raw data.
"""

import re
from typing import Dict, Any, List


def parse_zpl_to_raw(script: str) -> Dict[str, Any]:
    """
    Extract ALL data from a ZPL script — no field name assumptions.
    
    Returns a dict with:
      - text_blocks: list of {x, y, text, font_size} for every ^FD
      - barcodes: list of {type, data, x, y, height} for every barcode command
      - graphics: list of {type, x, y, size} for every graphic element
      - zpl_commands: set of all ZPL command types found (^BC, ^BD, ^GFA, etc.)
      - raw_texts: list of all ^FD text values (flat, for simple searching)
    """
    raw = {
        "text_blocks": [],
        "barcodes": [],
        "graphics": [],
        "zpl_commands": set(),
        "raw_texts": [],
    }

    # ── Extract all positioned text blocks ──
    # Match ^FO x,y followed eventually by ^FD content ^FS
    for fo_match in re.finditer(r"\^FO(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)", script):
        x = float(fo_match.group(1))
        y = float(fo_match.group(2))
        rest = script[fo_match.end():]

        # Extract font size if ^A0N,size,size is present before ^FD
        font_size = 0
        font_match = re.match(r"[^\^]*\^A0N,(\d+),(\d+)", rest)
        if font_match:
            font_size = int(font_match.group(1))

        # Find ^FD before next ^FO
        fd_match = re.search(r"\^FD(.*?)\^FS", rest, re.DOTALL)
        next_fo = re.search(r"\^FO\d", rest)

        if fd_match:
            if next_fo is None or fd_match.start() < next_fo.start():
                text = fd_match.group(1).strip()
                if text:
                    raw["text_blocks"].append({
                        "x": x, "y": y,
                        "text": text,
                        "font_size": font_size,
                    })
                    raw["raw_texts"].append(text)

    # Also catch ^FD blocks that aren't preceded by ^FO (rare but possible)
    for fd_match in re.finditer(r"\^FD(.*?)\^FS", script, re.DOTALL):
        text = fd_match.group(1).strip()
        if text and text not in raw["raw_texts"]:
            raw["raw_texts"].append(text)

    # ── Extract all barcode commands and their data ──
    barcode_commands = {
        "BC": "CODE128",
        "BD": "MAXICODE",
        "B7": "PDF417",
        "BX": "DATAMATRIX",
        "BQ": "QRCODE",
        "BA": "CODE39",
        "B2": "INTERLEAVED2OF5",
        "B3": "CODE39",
        "BE": "EAN13",
        "B8": "EAN8",
    }

    for cmd, barcode_type in barcode_commands.items():
        # Pattern: ^FO x,y ... ^Bx params ... ^FD data ^FS
        pattern = rf"\^FO(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)[^\^]*(?:\^[A-Z][^\^]*)*\^{cmd}([^\^]*?)(?:\^[A-Z][^\^]*)*\^FD(.*?)\^FS"
        for match in re.finditer(pattern, script, re.DOTALL):
            x = float(match.group(1))
            y = float(match.group(2))
            params = match.group(3).strip()
            data = match.group(4).strip().lstrip(">;")

            # Extract height from params if available
            height = 0
            height_match = re.search(r"N?,?(\d+)", params)
            if height_match:
                height = int(height_match.group(1))

            raw["barcodes"].append({
                "type": barcode_type,
                "data": data,
                "x": x, "y": y,
                "height": height,
            })

        # Also catch barcode commands without ^FO positioning
        pattern2 = rf"\^{cmd}([^\^]*?)\^FD(.*?)\^FS"
        for match in re.finditer(pattern2, script, re.DOTALL):
            data = match.group(2).strip().lstrip(">;")
            already_found = any(b["data"] == data for b in raw["barcodes"])
            if not already_found and data:
                raw["barcodes"].append({
                    "type": barcode_type,
                    "data": data,
                    "x": 0, "y": 0,
                    "height": 0,
                })

    # MaxiCode special: ^BD can appear as ^BD3^FH^FD... (with ^FH hex indicator)
    for match in re.finditer(r"\^BD(\d?)(?:\^FH)?\^FD(.*?)\^FS", script, re.DOTALL):
        data = match.group(2).strip()
        already_found = any(b["data"] == data and b["type"] == "MAXICODE" for b in raw["barcodes"])
        if not already_found and data:
            raw["barcodes"].append({
                "type": "MAXICODE",
                "data": data,
                "x": 0, "y": 0,
                "height": 0,
            })

    # ── Extract graphic elements ──
    for match in re.finditer(r"\^FO(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)[^\^]*\^GFA,(\d+),(\d+),(\d+),", script):
        raw["graphics"].append({
            "type": "GFA",
            "x": float(match.group(1)),
            "y": float(match.group(2)),
            "total_bytes": int(match.group(3)),
            "bytes_per_row": int(match.group(5)),
        })

    # Also catch ^GFA without ^FO
    for match in re.finditer(r"\^GFA,(\d+),(\d+),(\d+),", script):
        total = int(match.group(1))
        already_found = any(g["total_bytes"] == total for g in raw["graphics"])
        if not already_found:
            raw["graphics"].append({
                "type": "GFA",
                "x": 0, "y": 0,
                "total_bytes": total,
                "bytes_per_row": int(match.group(3)),
            })

    # ── Catalog all ZPL commands present ──
    for match in re.finditer(r"\^([A-Z][A-Z0-9])", script):
        raw["zpl_commands"].add("^" + match.group(1))

    # Convert set to list for JSON serialization
    raw["zpl_commands"] = sorted(list(raw["zpl_commands"]))

    # Sort text blocks by position (top to bottom, left to right)
    raw["text_blocks"].sort(key=lambda b: (b["y"], b["x"]))

    return raw


def parse_zpl_script(script: str) -> Dict[str, Any]:
    """
    Backward-compatible wrapper.
    
    Returns the raw extraction AND a basic parsed dict with common
    field names for backward compatibility with existing code.
    
    The raw data is stored under "_raw" key for the new validator to use.
    """
    raw = parse_zpl_to_raw(script)

    # Build backward-compatible parsed dict
    parsed = {}
    parsed["_raw"] = raw

    # Basic extractions that don't assume carrier-specific naming
    _extract_basics(parsed, raw, script)

    return parsed


def _extract_basics(parsed: dict, raw: dict, script: str):
    """
    Extract basic fields for backward compatibility.
    These are generic ZPL patterns that work across all carriers.
    """
    texts = raw["raw_texts"]
    barcodes = raw["barcodes"]

    # Tracking number — from barcode data or TRACKING #: text
    for bc in barcodes:
        if bc["type"] == "CODE128":
            data = bc["data"]
            # UPS: 1Z + 16 alphanumeric
            if re.match(r"^1Z[A-Z0-9]{16}$", data):
                parsed["tracking_number"] = data
                parsed["barcode"] = data
                break
            # DHL: JD + digits
            if re.match(r"^JD\d{18,}$", data):
                parsed["tracking_number"] = data
                parsed["barcode"] = data
                break
            # FedEx/Generic: 12-22 digit barcode
            if re.match(r"^\d{12,22}$", data):
                parsed.setdefault("tracking_number", data)
                parsed.setdefault("barcode", data)

    # From TRACKING #: text
    for t in texts:
        if "TRACKING" in t.upper() and "#" in t:
            match = re.search(r"TRACKING\s*#\s*:\s*([\dA-Z\s]+)", t, re.IGNORECASE)
            if match:
                parsed.setdefault("tracking_number", match.group(1).strip().replace(" ", ""))

    # Weight — standalone number + KG/LBS
    for t in texts:
        if re.match(r"^\d+(\.\d+)?\s+(KG|LBS?)\s*$", t.strip(), re.IGNORECASE):
            if not any(kw in t.upper() for kw in ["SHP WT", "SHP DWT"]):
                parsed["weight"] = t.strip()
                break

    # Piece count — N OF X
    for t in texts:
        match = re.search(r"\b(\d+)\s+OF\s+(\d+|_+)\b", t, re.IGNORECASE)
        if match:
            parsed["piece_count"] = match.group(0)
            break

    # Service type — from known service prefixes
    for t in texts:
        upper = t.upper().strip()
        if any(upper.startswith(p) for p in ["UPS ", "DHL ", "FEDEX ", "TNT ", "DPD "]):
            if len(upper) <= 40:
                parsed["service_type"] = upper
                break

    # Sender/receiver addresses — from spatial position
    ship_to_y = None
    for block in raw["text_blocks"]:
        if block["text"].upper().strip() in ("SHIP", "SHIP TO:", "SHIP TO"):
            ship_to_y = block["y"]
            break

    if ship_to_y:
        sender_lines = []
        receiver_lines = []
        for block in raw["text_blocks"]:
            if block["text"].upper().strip() in ("SHIP", "TO:", "SHIP TO:", "TO"):
                continue
            if block["y"] < ship_to_y and block["x"] < 400:
                # Skip package info in top-right
                if block["x"] > 400:
                    continue
                if any(kw in block["text"].upper() for kw in ["SHP#", "SHP WT", "SHP DWT", "DATE:"]):
                    continue
                if re.match(r"^\d+(\.\d+)?\s+(KG|LBS)", block["text"].strip(), re.IGNORECASE):
                    continue
                if re.match(r"^\d+\s+OF\s+", block["text"].strip(), re.IGNORECASE):
                    continue
                sender_lines.append(block["text"].strip())
            elif block["x"] >= 200 and block["y"] >= ship_to_y - 30 and block["y"] < ship_to_y + 160:
                receiver_lines.append(block["text"].strip())

        if sender_lines:
            parsed["sender_address"] = " | ".join(sender_lines)
        if receiver_lines:
            parsed["receiver_address"] = " | ".join(receiver_lines)

    # Billing
    for t in texts:
        if t.upper().startswith("BILLING"):
            match = re.search(r"BILLING\s*:\s*(.+)", t, re.IGNORECASE)
            if match:
                parsed["billing"] = match.group(1).strip()
                break

    # Country
    country_names = {
        "GERMANY", "FRANCE", "SPAIN", "PORTUGAL", "ITALY", "NETHERLANDS",
        "BELGIUM", "AUSTRIA", "SWITZERLAND", "SWEDEN", "DENMARK", "NORWAY",
        "FINLAND", "POLAND", "IRELAND", "UNITED KINGDOM", "UK", "USA",
        "UNITED STATES", "CANADA", "BRAZIL", "MEXICO", "JAPAN", "CHINA",
        "INDIA", "AUSTRALIA", "SINGAPORE", "HUNGARY", "ROMANIA", "GREECE",
        "CZECH REPUBLIC", "TURKEY", "CROATIA", "BULGARIA", "SERBIA",
        "LUXEMBOURG", "SLOVAKIA", "SLOVENIA", "ESTONIA", "LATVIA", "LITHUANIA",
    }
    for t in texts:
        if t.upper().strip() in country_names:
            parsed["destination_country"] = t.upper().strip()
            break