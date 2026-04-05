import re
from typing import Dict, Any, List, Tuple, Optional

# Header patterns for date fields on ANY carrier label
DATE_HEADER_PATTERNS = [
    r"pickup\s+date",           # DHL, FedEx
    r"ship(?:ment)?\s+date",    # UPS, generic
    r"ship\s+date",             # UPS
    r"dispatch\s+date",         # TNT, Royal Mail
    r"collection\s+date",       # DPD, Hermes
    r"label\s+(?:print(?:ing)?\s+)?date",  # Any carrier
    r"date\s+of\s+shipment",    # Generic
    r"print\s+date",            # Generic
    r"mailing\s+date",          # USPS
]
 
# What a date value looks like (carrier-agnostic)
DATE_VALUE_PATTERN = re.compile(
    r"^\d{4}[-/]\d{2}[-/]\d{2}$"       # 2026-03-31 (ISO)
    r"|^\d{2}[-/]\d{2}[-/]\d{4}$"      # 31-03-2026 (EU) or 03/31/2026 (US)
    r"|^\d{2}[-/]\d{2}[-/]\d{2}$"      # 31-03-26 (short year)
    r"|^\d{8}$"                         # 20260331 (compact)
)


def parse_zpl_script(script: str) -> Dict[str, Any]:
    """
    Parse a ZPL script and extract structured data fields.

    Uses a three-layer approach:
    1. Spatial parsing: extract ^FO x,y positions + ^FD content to understand label layout
    2. Semantic parsing: detect label sections (ship-from, ship-to, tracking, service, etc.)
    3. Field decomposition: split composite fields (postal+city lines, tracking structure)

    Works for UPS, DHL, FedEx, and other carrier label formats.
    """
    parsed = {}

    # ── Layer 1: Spatial extraction ──
    positioned_blocks = _extract_positioned_blocks(script)
    fd_blocks = [b["text"] for b in positioned_blocks if b["text"]]
    clean_blocks = [block.strip() for block in re.findall(r"\^FD(.*?)\^FS", script, re.DOTALL) if block.strip()]

    # ── Layer 1b: Extract barcode data ──
    barcode_data_blocks = re.findall(r"\^BC[^\^]*\^FD(.*?)\^FS", script, re.DOTALL)
    barcode_data = [b.strip().lstrip(">;") for b in barcode_data_blocks if b.strip()]

    # MaxiCode data (^BD commands)
    maxicode_data = re.findall(r"\^BD[^\^]*(?:\^FH)?\^FD(.*?)\^FS", script, re.DOTALL)

    # ── Layer 2: Semantic section detection ──
    sections = _detect_label_sections(positioned_blocks, clean_blocks, script)

    # ── Layer 3: Extract fields from detected sections ──

    # --- Tracking Number ---
    _extract_tracking_number(parsed, clean_blocks, barcode_data, sections)

    # --- Service Type ---
    _extract_service_type(parsed, clean_blocks, sections)

    # --- Ship-From Address (Sender) ---
    _extract_sender_address(parsed, sections, positioned_blocks, clean_blocks)

    # --- Ship-To Address (Receiver) ---
    _extract_receiver_address(parsed, sections, positioned_blocks, clean_blocks)

    # --- Postal Code (ship-to) ---
    _extract_postal_code(parsed, sections, clean_blocks, barcode_data)

    # --- Ship-to City ---
    _extract_city(parsed, sections, clean_blocks)

    # --- Country ---
    _extract_country(parsed, sections, clean_blocks)

    # --- Weight ---
    _extract_weight(parsed, clean_blocks)

    # --- Piece Count ---
    _extract_piece_count(parsed, clean_blocks)

    # --- License Plate ---
    _extract_license_plate(parsed, barcode_data, clean_blocks)

    # --- Routing Barcode ---
    _extract_routing_barcode(parsed, barcode_data, clean_blocks, maxicode_data)

    # --- Barcode Type ---
    _extract_barcode_type(parsed, script)

    # --- Billing ---
    _extract_billing(parsed, clean_blocks)

    # --- Description ---
    _extract_description(parsed, clean_blocks)

    # --- Reference Number ---
    _extract_reference(parsed, clean_blocks)

    # --- Date ---
    _extract_date(parsed, clean_blocks)

    return parsed


# ═══════════════════════════════════════════════════════════════
# LAYER 1: SPATIAL EXTRACTION
# ═══════════════════════════════════════════════════════════════

def _extract_positioned_blocks(script: str) -> List[Dict]:
    """
    Extract all ^FO positioned ^FD text blocks with their x,y coordinates.
    Returns list of {x, y, text, raw} sorted by y then x.
    """
    blocks = []

    # Find each ^FO position, then look for the next ^FD...^FS after it
    for fo_match in re.finditer(r"\^FO(\d+),(\d+)", script):
        x, y = int(fo_match.group(1)), int(fo_match.group(2))
        rest = script[fo_match.end():]
        # Stop looking if we hit another ^FO before finding ^FD
        fd_match = re.search(r"\^FD(.*?)\^FS", rest, re.DOTALL)
        next_fo = re.search(r"\^FO\d+,\d+", rest)
        if fd_match:
            # Only use this ^FD if it comes before the next ^FO (or there is no next ^FO)
            if next_fo is None or fd_match.start() < next_fo.start():
                text = fd_match.group(1).strip()
                if text:
                    blocks.append({"x": x, "y": y, "text": text, "raw": ""})

    # Sort by y (top to bottom), then x (left to right)
    blocks.sort(key=lambda b: (b["y"], b["x"]))
    return blocks


# ═══════════════════════════════════════════════════════════════
# LAYER 2: SEMANTIC SECTION DETECTION
# ═══════════════════════════════════════════════════════════════

def _detect_label_sections(positioned_blocks: List[Dict], clean_blocks: List[str], script: str = "") -> Dict:
    """
    Detect label sections based on spatial layout and semantic markers.

    Standard shipping label layout (top to bottom):
    - Ship-from block (top-left, small font)
    - Package info block (top-right: weight, count, SHP#, date)
    - "SHIP TO:" marker + ship-to address block
    - Routing section (MaxiCode, routing code, postal barcode)
    - Service title + tracking barcode
    - Additional info (billing, description, references)
    """
    sections = {
        "ship_from_blocks": [],
        "ship_to_blocks": [],
        "ship_to_marker_y": None,
        "tracking_block": None,
        "service_block": None,
        "separator_lines": [],
    }

    # Find "SHIP" + "TO:" markers or combined "SHIP TO:"
    ship_to_y = None
    for i, block in enumerate(positioned_blocks):
        text_upper = block["text"].upper().strip()
        if text_upper in ("SHIP", "SHIP TO:", "SHIP TO"):
            ship_to_y = block["y"]
            # Check if next block is "TO:" at similar y
            if text_upper == "SHIP" and i + 1 < len(positioned_blocks):
                next_b = positioned_blocks[i + 1]
                if next_b["text"].upper().strip() in ("TO:", "TO") and abs(next_b["y"] - block["y"]) < 40:
                    ship_to_y = min(block["y"], next_b["y"])
            break

    sections["ship_to_marker_y"] = ship_to_y

    # Find horizontal separator lines (^GB commands with large width and zero/small height)
    for match in re.finditer(r"\^FO(\d+),(\d+)\^GB(\d+),(\d+),(\d+)", script):
        x, y, w, h, thickness = [int(match.group(i)) for i in range(1, 6)]
        if w > 200 and h <= 10:  # horizontal line
            sections["separator_lines"].append(y)

    sections["separator_lines"].sort()

    # Find "TRACKING #:" block
    for block in positioned_blocks:
        if "TRACKING" in block["text"].upper() and "#" in block["text"]:
            sections["tracking_block"] = block
            break

    # Find service type block (UPS STANDARD, DHL EXPRESS, etc.)
    service_keywords = [
        "UPS STANDARD", "UPS EXPRESS", "UPS SAVER", "UPS EXPEDITED", "UPS GROUND",
        "DHL EXPRESS", "DHL EUROPACK", "DHL EUROPREMIUM", "DHL PARCEL",
        "FEDEX GROUND", "FEDEX EXPRESS", "FEDEX HOME", "FEDEX PRIORITY",
        "STANDARD", "EXPRESS", "PRIORITY", "ECONOMY", "OVERNIGHT", "GROUND", "SAVER",
    ]
    for block in positioned_blocks:
        text_upper = block["text"].upper().strip()
        for kw in service_keywords:
            if kw in text_upper:
                sections["service_block"] = block
                break
        if sections["service_block"]:
            break

    # Classify blocks into ship-from vs ship-to based on SHIP TO marker
    if ship_to_y is not None:
        # Determine the x-column used by ship-to address lines
        # (typically x >= 200-260, right of the "SHIP TO:" label)
        ship_to_x_threshold = 200

        for block in positioned_blocks:
            text_upper = block["text"].upper().strip()
            # Skip markers themselves
            if text_upper in ("SHIP", "TO:", "SHIP TO:", "TO", "SHIP TO"):
                continue
            # Skip package info (typically x > 400)
            if block["x"] > 400 and block["y"] < ship_to_y + 150:
                continue

            # Ship-to detection: blocks at the ship-to x-column, near or below the marker
            # Some labels (UPS) start the name slightly above the "SHIP TO:" text
            # so we allow up to 30px above the marker if x >= ship_to_x_threshold
            is_ship_to_column = block["x"] >= ship_to_x_threshold
            is_near_or_below_marker = block["y"] >= ship_to_y - 30
            is_within_ship_to_zone = block["y"] < ship_to_y + 150

            if is_ship_to_column and is_near_or_below_marker and is_within_ship_to_zone:
                sections["ship_to_blocks"].append(block)
            elif block["y"] < ship_to_y - 30 and block["x"] < 400:
                sections["ship_from_blocks"].append(block)
            elif block["y"] < ship_to_y and block["x"] < ship_to_x_threshold:
                sections["ship_from_blocks"].append(block)

    return sections


# ═══════════════════════════════════════════════════════════════
# LAYER 3: FIELD EXTRACTION
# ═══════════════════════════════════════════════════════════════

def _extract_tracking_number(parsed, clean_blocks, barcode_data, sections):
    """Extract tracking number from barcode data, TRACKING #: label, or pattern matching."""

    # Method 1: From "TRACKING #:" text block
    for block in clean_blocks:
        if "TRACKING" in block.upper() and "#" in block:
            # Extract the number after "TRACKING #:"
            match = re.search(r"TRACKING\s*#\s*:\s*([\dA-Z\s]+)", block, re.IGNORECASE)
            if match:
                raw = match.group(1).strip().replace(" ", "")
                if len(raw) >= 8:
                    parsed["tracking_number"] = raw
                    break

    # Method 2: From barcode data (Code 128 barcodes)
    if "tracking_number" not in parsed:
        for bd in barcode_data:
            clean_bd = bd.strip()
            # UPS: 1Z followed by 16 alphanumeric
            if re.match(r"^1Z[A-Z0-9]{16}$", clean_bd):
                parsed["tracking_number"] = clean_bd
                break
            # DHL: JD followed by digits (20+ chars)
            if re.match(r"^JD\d{18,}$", clean_bd):
                parsed["tracking_number"] = clean_bd
                break
            # FedEx: 12-22 digits
            if re.match(r"^\d{12,22}$", clean_bd):
                parsed["tracking_number"] = clean_bd
                break
            # Generic: long alphanumeric barcode (likely tracking)
            if re.match(r"^[A-Z0-9]{12,35}$", clean_bd) and not clean_bd.startswith("42"):
                parsed["tracking_number"] = clean_bd
                break

    # Method 3: Pattern matching in all text blocks
    tracking_patterns = [
        (r"\b1Z[A-Z0-9]{16}\b", "UPS"),
        (r"\b[A-Z]{2}\d{18,22}\b", "DHL"),
        (r"\b\d{12,22}\b", "Generic"),
        (r"\b[A-Z]{4}\d{10,}\b", "FedEx"),
    ]
    if "tracking_number" not in parsed:
        for pattern, _label in tracking_patterns:
            for block in clean_blocks:
                match = re.search(pattern, block.replace(" ", ""))
                if match:
                    parsed["tracking_number"] = match.group(0)
                    break
            if "tracking_number" in parsed:
                break

    # Also set barcode field
    if "tracking_number" in parsed and "barcode" not in parsed:
        parsed["barcode"] = parsed["tracking_number"]

    # Extract shipment_number alias
    if "tracking_number" in parsed:
        parsed["shipment_number"] = parsed["tracking_number"]


def _extract_service_type(parsed, clean_blocks, sections):
    """Extract service type from service block or pattern matching."""

    # Method 1: From detected service block
    if sections.get("service_block"):
        parsed["service_type"] = sections["service_block"]["text"].strip()
        return

    # Method 2: Pattern matching
    service_patterns = [
        # Carrier-prefixed services (most specific first)
        r"\b(UPS\s+(?:STANDARD|EXPRESS|SAVER|EXPEDITED|GROUND|EXPRESS\s*12:?\s*00|WORLDWIDE\s+EXPRESS))\b",
        r"\b(DHL\s+(?:EXPRESS|EUROPACK|EUROPREMIUM|HOME\s*DELIVERY|FREIGHT|PARCEL|EXPRESS\s+WORLDWIDE))\b",
        r"\b(FEDEX\s+(?:GROUND|EXPRESS|HOME\s*DELIVERY|PRIORITY|INTERNATIONAL|OVERNIGHT|2DAY|FREIGHT))\b",
        # Generic service types
        r"\b(EXPRESS|STANDARD|PRIORITY|ECONOMY|OVERNIGHT|GROUND|NEXT\s*DAY|SAVER)\b",
        # Product codes
        r"\b(WPX|DOX|ECX|ESI|ESU|EPX)\b",
    ]
    for pattern in service_patterns:
        for block in clean_blocks:
            match = re.search(pattern, block, re.IGNORECASE)
            if match:
                parsed["service_type"] = match.group(0).strip()
                return


def _extract_sender_address(parsed, sections, positioned_blocks, clean_blocks):
    """
    Extract sender (ship-from) address.

    Strategy:
    1. Use spatially-detected ship-from blocks (above SHIP TO marker, left side)
    2. Fall back to From:/FROM: label detection
    3. Fall back to first few blocks on the label (usually ship-from)
    """
    sender_lines = []

    # Method 1: Spatial detection
    if sections.get("ship_from_blocks"):
        for block in sections["ship_from_blocks"]:
            text = block["text"].strip()
            if text and len(text) > 1:
                # Skip weight, piece count, SHP# lines
                if any(kw in text.upper() for kw in ["SHP#", "SHP WT", "SHP DWT", "DATE:", "OF _", "OF 1", "KG", "LBS"]):
                    continue
                sender_lines.append(text)

    # Method 2: From:/FROM: label detection
    if not sender_lines:
        address_mode = None
        for block in clean_blocks:
            block_lower = block.lower().strip()
            if block_lower.startswith("from") or block_lower == "from:":
                address_mode = "sender"
                continue
            elif any(block_lower.startswith(x) for x in ["to", "ship"]):
                address_mode = None
                continue
            elif any(kw in block_lower for kw in ["phone:", "weight:", "account", "shipment", "date:", "tracking"]):
                address_mode = None
                continue
            if address_mode == "sender" and len(block) > 2 and len(sender_lines) < 6:
                sender_lines.append(block)

    # Method 3: First blocks are usually ship-from (if we have a SHIP TO marker)
    if not sender_lines and sections.get("ship_to_marker_y"):
        ship_to_y = sections["ship_to_marker_y"]
        for block in positioned_blocks:
            if block["y"] < ship_to_y and block["x"] < 400:
                text = block["text"].strip()
                if text and len(text) > 1:
                    if any(kw in text.upper() for kw in ["SHP#", "SHP WT", "SHP DWT", "DATE:", "KG PAK", "LBS PAK"]):
                        continue
                    # Skip if it looks like weight/count
                    if re.match(r"^\d+(\.\d+)?\s*(KG|LBS?|OF)\b", text, re.IGNORECASE):
                        continue
                    sender_lines.append(text)

    if sender_lines:
        parsed["sender_address"] = " | ".join(sender_lines)
        parsed["ship_from_address"] = parsed["sender_address"]
        if sender_lines:
            parsed["sender_name"] = sender_lines[0]


def _extract_receiver_address(parsed, sections, positioned_blocks, clean_blocks):
    """
    Extract receiver (ship-to) address.

    Strategy:
    1. Use spatially-detected ship-to blocks (right of SHIP TO label, below marker)
    2. Fall back to To:/TO: label detection
    """
    receiver_lines = []

    # Method 1: Spatial detection
    if sections.get("ship_to_blocks"):
        for block in sections["ship_to_blocks"]:
            text = block["text"].strip()
            if text and len(text) > 1:
                receiver_lines.append(text)

    # Method 2: Semantic detection
    if not receiver_lines:
        address_mode = None
        seen_ship_to = False
        for i, block in enumerate(clean_blocks):
            block_upper = block.upper().strip()

            # Detect "SHIP" + "TO:" pattern (two separate blocks)
            if block_upper == "SHIP" and i + 1 < len(clean_blocks):
                next_upper = clean_blocks[i + 1].upper().strip()
                if next_upper in ("TO:", "TO"):
                    seen_ship_to = True
                    address_mode = "receiver"
                    continue
            if block_upper in ("TO:", "TO") and seen_ship_to:
                continue  # skip the "TO:" block itself

            # Standard "to:" or "ship to:" as single block
            block_lower = block.lower().strip()
            if block_lower.startswith("to") or block_lower.startswith("ship to"):
                address_mode = "receiver"
                continue

            # Stop conditions
            if address_mode == "receiver":
                if any(kw in block_lower for kw in ["tracking", "billing", "routing", "desc:", "ref #"]):
                    break
                # Stop at separator lines or barcodes
                if block.startswith("^") or len(block) < 2:
                    continue
                receiver_lines.append(block)
                if len(receiver_lines) >= 6:
                    break

    if receiver_lines:
        parsed["receiver_address"] = " | ".join(receiver_lines)
        parsed["ship_to_address"] = parsed["receiver_address"]
        if receiver_lines:
            parsed["receiver_name"] = receiver_lines[0]


def _extract_postal_code(parsed, sections, clean_blocks, barcode_data):
    """
    Extract ship-to postal code.

    Strategy:
    1. From postal barcode data (420xxxxx for domestic, 421xxxYYYYY for international)
    2. From ship-to address blocks (decompose "28229 VILLANUEVA DEL PARDILLO")
    3. Pattern matching in all blocks
    """
    # Method 1: Postal barcode (most reliable)
    for bd in barcode_data:
        clean_bd = bd.strip()
        # International: 421 + 3-digit country code + postal code
        intl_match = re.match(r"^421(\d{3})(.+)$", clean_bd)
        if intl_match:
            parsed["postal_code"] = intl_match.group(2).strip()
            parsed["ship_to_postal_code"] = parsed["postal_code"]
            return
        # Domestic US: 420 + postal code
        dom_match = re.match(r"^420(.+)$", clean_bd)
        if dom_match:
            parsed["postal_code"] = dom_match.group(1).strip()
            parsed["ship_to_postal_code"] = parsed["postal_code"]
            return

    # Method 2: From ship-to blocks - decompose postal code line
    ship_to_blocks = sections.get("ship_to_blocks", [])
    for block in ship_to_blocks:
        text = block["text"].strip()
        extracted = _extract_postal_from_line(text)
        if extracted:
            parsed["postal_code"] = extracted
            parsed["ship_to_postal_code"] = extracted
            return

    # Also try receiver_address if already parsed
    if "receiver_address" in parsed:
        for line in parsed["receiver_address"].split(" | "):
            extracted = _extract_postal_from_line(line)
            if extracted:
                parsed["postal_code"] = extracted
                parsed["ship_to_postal_code"] = extracted
                return

    # Method 3: Pattern matching in all blocks
    postal_patterns = [
        r"\b(\d{5})(-\d{4})?\b",                       # US / Spain / Germany
        r"\b(\d{4}\s?[A-Z]{2})\b",                     # Netherlands (1234 AB)
        r"\b([A-Z]\d[A-Z]\s?\d[A-Z]\d)\b",             # Canada
        r"\b([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})\b",       # UK
        r"\b(\d{3}\s?\d{2})\b",                         # Sweden (123 45)
    ]
    for pattern in postal_patterns:
        for block in clean_blocks:
            match = re.search(pattern, block)
            if match:
                parsed["postal_code"] = match.group(0).strip()
                parsed["ship_to_postal_code"] = parsed["postal_code"]
                return


def _extract_postal_from_line(text: str) -> Optional[str]:
    """
    Extract postal code from a composite line like "28229 VILLANUEVA DEL PARDILLO"
    or "5026 RH TILBURG" or "SW1A 1AA LONDON".
    """
    text = text.strip()

    # Pattern: digits at start followed by city name
    # "28229 VILLANUEVA DEL PARDILLO" → 28229
    match = re.match(r"^(\d{4,5})\s+[A-Z]", text)
    if match:
        return match.group(1)

    # Netherlands: "5026 RH TILBURG" → 5026 RH
    match = re.match(r"^(\d{4}\s?[A-Z]{2})\s+", text)
    if match:
        return match.group(1)

    # UK: "SW1A 1AA LONDON"
    match = re.match(r"^([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})\s+", text)
    if match:
        return match.group(1)

    # Canada: "H3W 2X7 MONTREAL"
    match = re.match(r"^([A-Z]\d[A-Z]\s?\d[A-Z]\d)\s+", text)
    if match:
        return match.group(1)

    return None


def _extract_city(parsed, sections, clean_blocks):
    """
    Extract ship-to city from address blocks.
    Decompose from postal code lines or use the line above country.
    """
    # Method 1: From ship-to blocks — find the postal+city line
    ship_to_blocks = sections.get("ship_to_blocks", [])
    for block in ship_to_blocks:
        text = block["text"].strip()
        city = _extract_city_from_line(text)
        if city:
            parsed["ship_to_city"] = city
            return

    # Method 2: From receiver_address
    if "receiver_address" in parsed:
        for line in parsed["receiver_address"].split(" | "):
            city = _extract_city_from_line(line.strip())
            if city:
                parsed["ship_to_city"] = city
                return


def _extract_city_from_line(text: str) -> Optional[str]:
    """
    Extract city name from a composite postal+city line.
    "28229 VILLANUEVA DEL PARDILLO" → "VILLANUEVA DEL PARDILLO"
    "5026 RH TILBURG" → "TILBURG"
    """
    text = text.strip()

    # "28229 VILLANUEVA DEL PARDILLO" — digits then city
    match = re.match(r"^\d{4,5}\s+(.+)$", text)
    if match:
        return match.group(1).strip()

    # Netherlands: "5026 RH TILBURG"
    match = re.match(r"^\d{4}\s?[A-Z]{2}\s+(.+)$", text)
    if match:
        return match.group(1).strip()

    # UK: "SW1A 1AA LONDON"
    match = re.match(r"^[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2}\s+(.+)$", text)
    if match:
        return match.group(1).strip()

    return None


def _extract_country(parsed, sections, clean_blocks):
    """Extract destination country from label blocks."""
    country_names_to_codes = {
        "GERMANY": "DE", "DEUTSCHLAND": "DE",
        "FRANCE": "FR",
        "SWEDEN": "SE", "SVERIGE": "SE",
        "SWITZERLAND": "CH", "SCHWEIZ": "CH",
        "NETHERLANDS": "NL", "NEDERLAND": "NL",
        "BELGIUM": "BE", "BELGIQUE": "BE",
        "AUSTRIA": "AT", "OSTERREICH": "AT", "ÖSTERREICH": "AT",
        "ITALY": "IT", "ITALIA": "IT",
        "SPAIN": "ES", "ESPAÑA": "ES", "ESPANA": "ES",
        "PORTUGAL": "PT",
        "UNITED KINGDOM": "GB", "UK": "GB", "GREAT BRITAIN": "GB",
        "IRELAND": "IE",
        "POLAND": "PL", "POLSKA": "PL",
        "DENMARK": "DK", "DANMARK": "DK",
        "NORWAY": "NO", "NORGE": "NO",
        "FINLAND": "FI", "SUOMI": "FI",
        "CZECH REPUBLIC": "CZ", "CZECHIA": "CZ",
        "UNITED STATES": "US", "USA": "US",
        "CANADA": "CA",
        "AUSTRALIA": "AU",
        "JAPAN": "JP",
        "CHINA": "CN",
        "INDIA": "IN",
        "BRAZIL": "BR",
        "MEXICO": "MX",
        "PHILIPPINES": "PH",
        "SINGAPORE": "SG",
        "SOUTH KOREA": "KR", "KOREA": "KR",
        "HUNGARY": "HU",
        "ROMANIA": "RO",
        "GREECE": "GR",
        "TURKEY": "TR",
        "RUSSIA": "RU",
        "UKRAINE": "UA",
        "LUXEMBOURG": "LU",
        "SLOVAKIA": "SK",
        "SLOVENIA": "SI",
        "CROATIA": "HR",
        "BULGARIA": "BG",
        "SERBIA": "RS",
        "ESTONIA": "EE",
        "LATVIA": "LV",
        "LITHUANIA": "LT",
    }

    # Check ship-to blocks first (destination country is in ship-to section)
    ship_to_blocks = sections.get("ship_to_blocks", [])
    for block in ship_to_blocks:
        upper = block["text"].upper().strip()
        if upper in country_names_to_codes:
            parsed["country_code"] = country_names_to_codes[upper]
            parsed["destination_country"] = upper
            return

    # Fallback: check all blocks
    for block in clean_blocks:
        block_upper = block.upper().strip()
        if block_upper in country_names_to_codes:
            parsed["country_code"] = country_names_to_codes[block_upper]
            parsed["destination_country"] = block_upper
            return

    # Fallback: standalone 2-letter code
    for block in clean_blocks:
        cc_match = re.match(r"^[A-Z]{2}$", block.strip())
        if cc_match:
            parsed["country_code"] = cc_match.group(0)
            return


def _extract_weight(parsed, clean_blocks):
    """Extract package weight."""
    # Look for standalone weight value (e.g., "1.0 KG", "50.5 KG")
    weight_pattern = r"\b(\d+(\.\d+)?)\s*(KG|LBS?|kg|lbs?)\b"
    for block in clean_blocks:
        # Skip lines that are clearly not just weight
        if any(kw in block.upper() for kw in ["SHP WT:", "SHP DWT:", "SHP#"]):
            continue
        match = re.match(r"^(\d+(\.\d+)?)\s*(KG|LBS?)\s*$", block.strip(), re.IGNORECASE)
        if match:
            parsed["weight"] = match.group(0).strip()
            return

    # Fallback: any weight pattern
    for block in clean_blocks:
        match = re.search(weight_pattern, block, re.IGNORECASE)
        if match:
            parsed["weight"] = match.group(0)
            return


def _extract_piece_count(parsed, clean_blocks):
    """Extract piece/package count (e.g., '1 OF 1', '2 OF 5')."""
    piece_pattern = r"\b(\d+)\s+OF\s+(\d+|_)\b"
    for block in clean_blocks:
        match = re.search(piece_pattern, block, re.IGNORECASE)
        if match:
            parsed["piece_count"] = match.group(0)
            return


def _extract_license_plate(parsed, barcode_data, clean_blocks):
    """Extract license plate (SSCC/EAN or ANSI) from barcodes or text."""
    for bd in barcode_data:
        # EAN SSCC: 00 + 18 digits
        sscc_match = re.search(r"00(\d{18})", bd)
        if sscc_match:
            parsed["license_plate"] = sscc_match.group(1)
            return
        # ANSI: JD prefix
        jd_match = re.search(r"(JD\d{2}\s*[\dA-Z\s]{10,})", bd)
        if jd_match:
            parsed["license_plate"] = jd_match.group(1).replace(" ", "")
            return

    # Check text blocks for (00) or (J) patterns
    for block in clean_blocks:
        lp_match = re.search(r"\(00\)\s*(\d{18,})", block)
        if lp_match:
            parsed["license_plate"] = lp_match.group(1)
            return
        lp_match2 = re.search(r"\(J\)\s*(JD[\dA-Z\s]+)", block)
        if lp_match2:
            parsed["license_plate"] = lp_match2.group(1).replace(" ", "")
            return


def _extract_routing_barcode(parsed, barcode_data, clean_blocks, maxicode_data):
    """Extract routing barcode data."""
    # Check barcode data
    for bd in barcode_data:
        if "2L" in bd or "403" in bd:
            parsed["routing_barcode"] = bd
            return

    # Check text blocks
    for block in clean_blocks:
        if "(2L)" in block or "(403)" in block:
            parsed["routing_barcode"] = block.replace("(2L)", "2L").replace("(403)", "403")
            return

    # UPS routing code (e.g., "ESP 285 4-30", "DEU 063 9-39")
    for block in clean_blocks:
        match = re.match(r"^[A-Z]{2,3}\s+\d{3}\s+\d-\d{2}$", block.strip())
        if match:
            parsed["routing_code"] = block.strip()
            return

    # MaxiCode contains routing data
    if maxicode_data:
        parsed["maxicode_data"] = maxicode_data[0].strip()


def _extract_barcode_type(parsed, script):
    """Detect barcode type from ZPL commands."""
    barcode_types = [
        ("^BC", "CODE128"),
        ("^BD", "MAXICODE"),
        ("^BX", "DATAMATRIX"),
        ("^BQ", "QR"),
        ("^BA", "CODE39"),
        ("^B2", "INTERLEAVED2OF5"),
    ]
    detected = []
    for cmd, btype in barcode_types:
        if cmd in script:
            detected.append(btype)
    if detected:
        parsed["barcode_type"] = detected[0]  # primary
        if len(detected) > 1:
            parsed["barcode_types"] = detected


def _extract_billing(parsed, clean_blocks):
    """Extract billing information."""
    for block in clean_blocks:
        if block.upper().startswith("BILLING"):
            match = re.search(r"BILLING\s*:\s*(.+)", block, re.IGNORECASE)
            if match:
                parsed["billing"] = match.group(1).strip()
                return


def _extract_description(parsed, clean_blocks):
    """Extract goods description."""
    for block in clean_blocks:
        if block.upper().startswith("DESC"):
            match = re.search(r"DESC\s*:\s*(.+)", block, re.IGNORECASE)
            if match:
                parsed["goods_description"] = match.group(1).strip()
                return


def _extract_reference(parsed, clean_blocks):
    """Extract reference numbers."""
    for block in clean_blocks:
        ref_match = re.search(r"REF\s*#?\s*\d*\s*:\s*(.+)", block, re.IGNORECASE)
        if ref_match:
            parsed["reference_number"] = ref_match.group(1).strip()
            return


def _extract_date(parsed, clean_blocks):
    """Extract shipment date."""
    for block in clean_blocks:
        date_match = re.search(r"DATE\s*:\s*(.+)", block, re.IGNORECASE)
        if date_match:
            parsed["shipment_date"] = date_match.group(1).strip()
            return