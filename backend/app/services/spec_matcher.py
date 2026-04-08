"""
Spec Matcher - Auto-detect carrier and spec from label content
==============================================================
Uses multiple signals from the raw ZPL data for more accurate matching:
- Tracking number format (1Z=UPS, JD=DHL, numeric=FedEx)
- Barcode types present (MaxiCode=UPS, PDF417=FedEx/DHL)
- Service title text (UPS STANDARD, DHL EXPRESS, FEDEX GROUND)
- Text patterns (BILLING:, DESC:, SHP#: = UPS style)
- Graphic elements (service icons)
- Address format (SHIP TO: style)
- Legal notice text (UPS Terms, DHL conditions, FedEx liability)
- Routing code format (XXX NNN N-NN = UPS, URSA codes = FedEx)
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict


COUNTRY_TO_REGION = {
    "DE": "europe", "FR": "europe", "GB": "europe", "UK": "europe",
    "NL": "europe", "BE": "europe", "AT": "europe", "CH": "europe",
    "IT": "europe", "ES": "europe", "PT": "europe", "PL": "europe",
    "SE": "europe", "DK": "europe", "NO": "europe", "FI": "europe",
    "IE": "europe", "CZ": "europe", "HU": "europe", "RO": "europe",
    "BG": "europe", "HR": "europe", "SK": "europe", "SI": "europe",
    "EE": "europe", "LV": "europe", "LT": "europe", "LU": "europe",
    "GR": "europe", "RS": "europe",
    "US": "us", "CA": "canada", "MX": "americas", "BR": "americas",
    "CN": "asia", "JP": "asia", "KR": "asia", "IN": "asia",
    "SG": "asia", "AU": "asia_pacific", "NZ": "asia_pacific",
    "AE": "middle_east", "SA": "middle_east", "ZA": "africa",
}

COUNTRY_NAMES_TO_CODE = {
    "NETHERLANDS": "NL", "GERMANY": "DE", "FRANCE": "FR",
    "SPAIN": "ES", "ITALY": "IT", "BELGIUM": "BE",
    "UNITED KINGDOM": "GB", "SWEDEN": "SE", "AUSTRIA": "AT",
    "SWITZERLAND": "CH", "POLAND": "PL", "DENMARK": "DK",
    "UNITED STATES": "US", "USA": "US", "CANADA": "CA",
    "AUSTRALIA": "AU", "JAPAN": "JP", "CHINA": "CN",
    "INDIA": "IN", "BRAZIL": "BR", "MEXICO": "MX",
    "SINGAPORE": "SG", "PORTUGAL": "PT", "IRELAND": "IE",
    "NORWAY": "NO", "FINLAND": "FI", "HUNGARY": "HU",
    "ROMANIA": "RO", "GREECE": "GR", "CZECH REPUBLIC": "CZ",
    "TURKEY": "TR", "CROATIA": "HR", "LUXEMBOURG": "LU",
    "POLAND": "PL",
}


# ═══════════════════════════════════════════════════════════════
# SERVICE NAME → CARRIER LOOKUP (carrier-agnostic, data-driven)
# ═══════════════════════════════════════════════════════════════
# This table maps service names that do NOT contain the carrier
# name itself. Services like "DHL EXPRESS" already match via
# substring, but "ECONOMY SELECT" does not contain "DHL".
# Add new services here as they're encountered — no code changes.

SERVICE_NAME_TO_CARRIER = {
    # DHL services that don't contain "DHL"
    "ECONOMY SELECT": "dhl",
    "EUROPLUS": "dhl",
    "EUROCONNECT": "dhl",
    "BREAKBULK EXPRESS": "dhl",
    "EXPRESS WORLDWIDE": "dhl",
    "EXPRESS EASY": "dhl",
    "EXPRESS ENVELOPE": "dhl",
    "EXPRESS 9:00": "dhl",
    "EXPRESS 10:30": "dhl",
    "EXPRESS 12:00": "dhl",
    "DOMESTIC EXPRESS": "dhl",
    "JETLINE": "dhl",
    "SPRINTLINE": "dhl",
    "SECURELINE": "dhl",
    "EUROPACK": "dhl",
    "JUMBO BOX": "dhl",
    "MEDICAL EXPRESS": "dhl",
    "SAME DAY": "dhl",
    "ESU": "dhl",
    "ESI": "dhl",
    "WPX": "dhl",
    # UPS services that don't contain "UPS"
    "NEXT DAY AIR": "ups",
    "2ND DAY AIR": "ups",
    "3 DAY SELECT": "ups",
    "GROUND": "ups",
    "WORLDWIDE EXPRESS": "ups",
    "WORLDWIDE SAVER": "ups",
    "WORLDWIDE EXPEDITED": "ups",
    # FedEx services that don't contain "FEDEX"
    "PRIORITY OVERNIGHT": "fedex",
    "STANDARD OVERNIGHT": "fedex",
    "FIRST OVERNIGHT": "fedex",
    "INTL PRIORITY": "fedex",
    "INTL ECONOMY": "fedex",
    "INTL FIRST": "fedex",
    "INTL CONNECT PLUS": "fedex",
    "SMARTPOST": "fedex",
    "HOME DELIVERY": "fedex",
    # TNT services
    "GLOBAL EXPRESS": "tnt",
    "12:00 EXPRESS": "tnt",
    "09:00 EXPRESS": "tnt",
    "ECONOMY EXPRESS": "tnt",
}

# ═══════════════════════════════════════════════════════════════
# BARCODE DATA PATTERNS (carrier-agnostic, regex-driven)
# ═══════════════════════════════════════════════════════════════
# Patterns matched against ALL barcode data in the label,
# not just the primary tracking number.

BARCODE_DATA_PATTERNS = {
    "ups": [
        re.compile(r"^1Z[A-Z0-9]{16}$"),                    # UPS tracking
        re.compile(r"^\[?\)?>01\d{2}1Z"),                    # UPS MaxiCode content
    ],
    "dhl": [
        re.compile(r"^JJD\d{10,}$"),                         # DHL license plate (JJD)
        re.compile(r"^JD0[01]\s?\d{4}\s?\d{4}\s?\d{4}"),     # DHL license plate (JD01 grouped)
        re.compile(r"^JD0[01]\d{10,}$"),                      # DHL license plate (JD01 flat)
        re.compile(r"^2L[A-Z]{2}\d+\+"),                      # DHL routing barcode (2L prefix)
        re.compile(r"^00\d{18}$"),                             # SSCC-18 (DHL uses these)
    ],
    "fedex": [
        re.compile(r"^\d{34}$"),                               # FedEx 2D barcode data
        re.compile(r"^\d{12}$"),                               # FedEx 12-digit tracking
        re.compile(r"^\d{15}$"),                               # FedEx 15-digit tracking
    ],
}

# ═══════════════════════════════════════════════════════════════
# TEXT PATTERNS — keywords found in label text (carrier-agnostic)
# ═══════════════════════════════════════════════════════════════

TEXT_KEYWORDS = {
    "ups": {
        "strong": ["UPS"],                          # 10 points each
        "medium": ["SHP#:", "BILLING:", "DESC:"],    # 5 points each
        "weak":   [],                                # 3 points each
    },
    "dhl": {
        "strong": ["DHL"],
        "medium": ["WAYBILL", "PICKUP DATE", "ECONOMY SELECT"],
        "weak":   ["HOLDER REF"],
    },
    "fedex": {
        "strong": ["FEDEX", "FED EX"],
        "medium": ["ORIGIN ID:", "URSA"],
        "weak":   ["CAD:", "HAL:"],
    },
    "tnt": {
        "strong": ["TNT"],
        "medium": [],
        "weak":   [],
    },
    "dpd": {
        "strong": ["DPD"],
        "medium": [],
        "weak":   [],
    },
}

# Routing code patterns
ROUTING_PATTERNS = {
    "ups":   re.compile(r"^[A-Z]{2,3}\s+\d{3}\s+\d-\d{2}$"),   # PRT 399 9-88
    "dhl":   re.compile(r"^2L[A-Z]{2}\d+\+"),                     # 2LPL30389+...
    "fedex": re.compile(r"^[A-Z]{2}\s+[A-Z]{4}$"),                # XH HKAA (URSA)
}


@dataclass
class LabelSignals:
    carrier: str = ""
    carrier_confidence: float = 0.0
    carrier_signals: List[str] = None
    origin_country: str = ""
    destination_country: str = ""
    origin_region: str = ""
    destination_region: str = ""
    service_type: str = ""
    tracking_number: str = ""
    is_international: bool = False
    is_domestic: bool = False

    def __post_init__(self):
        if self.carrier_signals is None:
            self.carrier_signals = []


@dataclass
class CarrierMatch:
    carrier_id: str
    carrier_name: str
    spec_name: str
    confidence: float
    match_reasons: List[str]
    is_best_match: bool = False

    def to_dict(self):
        return asdict(self)


def extract_label_signals(parsed_label: Dict) -> LabelSignals:
    """
    Extract carrier signals using ALL available data from the label.
    Uses both parsed fields and raw ZPL data for maximum accuracy.
    All detection is data-driven via lookup tables — no hardcoded if/else.
    """
    signals = LabelSignals()
    raw = parsed_label.get("_raw", {})
    texts = raw.get("raw_texts", []) if raw else []
    barcodes = raw.get("barcodes", []) if raw else []
    zpl_commands = raw.get("zpl_commands", []) if raw else []
    all_text = " ".join(texts).upper()

    carrier_scores = {}
    carrier_reasons = {}
    for carrier in TEXT_KEYWORDS:
        carrier_scores[carrier] = 0
        carrier_reasons[carrier] = []

    # ── Signal 1: Tracking number format ──
    tracking = parsed_label.get("tracking_number", "")
    signals.tracking_number = tracking

    if tracking:
        if re.match(r"^1Z[A-Z0-9]{16}$", tracking):
            carrier_scores["ups"] += 30
            carrier_reasons["ups"].append("tracking 1Z format")
        elif re.match(r"^JD\d{18,}$", tracking) or re.match(r"^JJD\d{10,}$", tracking):
            carrier_scores["dhl"] += 30
            carrier_reasons["dhl"].append("tracking JD/JJD format")
        elif re.match(r"^\d{12,22}$", tracking):
            carrier_scores["fedex"] += 15
            carrier_reasons["fedex"].append("numeric tracking")

    # ── Signal 2: ALL barcode data (not just tracking) ──
    # This catches DHL license plates (JJD...), routing (2L...), etc.
    for bc in barcodes:
        data = bc.get("data", "").strip()
        if not data:
            continue
        for carrier, patterns in BARCODE_DATA_PATTERNS.items():
            for pattern in patterns:
                if pattern.match(data):
                    carrier_scores[carrier] += 20
                    reason = f"barcode match: {data[:25]}..."
                    if reason not in carrier_reasons[carrier]:
                        carrier_reasons[carrier].append(reason)
                    break

    # Also scan raw text for barcode data (catches ^FD content not in barcodes list)
    for carrier, patterns in BARCODE_DATA_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(all_text):
                if carrier_scores[carrier] < 20:  # Don't double-count
                    carrier_scores[carrier] += 15
                    carrier_reasons[carrier].append(f"barcode pattern in text")

    # ── Signal 3: Barcode types ──
    barcode_types = set(bc.get("type", "") for bc in barcodes)
    if "MAXICODE" in barcode_types:
        carrier_scores["ups"] += 20
        carrier_reasons["ups"].append("MaxiCode present")

    # ── Signal 4: Service title — exact lookup then substring ──
    service = parsed_label.get("service_type", "").upper().strip()
    signals.service_type = service

    if service:
        # First: check the lookup table for services without carrier name
        matched_carrier = SERVICE_NAME_TO_CARRIER.get(service)
        if matched_carrier:
            carrier_scores[matched_carrier] += 25
            carrier_reasons[matched_carrier].append(f"service: {service}")
        else:
            # Second: check if carrier name appears as substring in service
            for carrier in carrier_scores:
                if carrier.upper() in service:
                    carrier_scores[carrier] += 25
                    carrier_reasons[carrier].append(f"service: {service}")
                    break

    # ── Signal 5: Text content — data-driven keyword scan ──
    for carrier, keyword_groups in TEXT_KEYWORDS.items():
        for kw in keyword_groups.get("strong", []):
            if kw in all_text:
                carrier_scores[carrier] += 10
                carrier_reasons[carrier].append(f"{kw} text found")
        for kw in keyword_groups.get("medium", []):
            if kw in all_text:
                carrier_scores[carrier] += 5
                carrier_reasons[carrier].append(f"{kw} text")
        for kw in keyword_groups.get("weak", []):
            if kw in all_text:
                carrier_scores[carrier] += 3
                carrier_reasons[carrier].append(f"{kw} text")

    # ── Signal 6: Legal notice text ──
    for t in texts:
        t_lower = t.lower()
        if "ups terms" in t_lower or "ups.com" in t_lower:
            carrier_scores["ups"] += 10
            carrier_reasons["ups"].append("UPS legal notice")
            break
        if "dhl" in t_lower and ("liability" in t_lower or "conditions" in t_lower):
            carrier_scores["dhl"] += 10
            carrier_reasons["dhl"].append("DHL legal notice")
            break
        if "federal express" in t_lower or "fedex.com" in t_lower:
            carrier_scores["fedex"] += 10
            carrier_reasons["fedex"].append("FedEx legal notice")
            break

    # ── Signal 7: Routing code format ──
    for t in texts:
        for carrier, pattern in ROUTING_PATTERNS.items():
            if pattern.match(t.strip()):
                carrier_scores[carrier] += 10
                carrier_reasons[carrier].append(f"routing: {t.strip()[:20]}")
                break

    # ── Signal 8: Graphic elements ──
    graphics = raw.get("graphics", []) if raw else []
    if graphics and "^BD" in zpl_commands:
        carrier_scores["ups"] += 5
        carrier_reasons["ups"].append("MaxiCode + graphic icon")

    # ── Determine winner ──
    best_carrier = max(carrier_scores, key=carrier_scores.get)
    best_score = carrier_scores[best_carrier]

    if best_score > 0:
        signals.carrier = best_carrier
        signals.carrier_confidence = min(best_score / 80.0, 1.0)
        signals.carrier_signals = carrier_reasons[best_carrier]
    else:
        signals.carrier = ""
        signals.carrier_confidence = 0

    # Debug: show all scores
    nonzero = {k: v for k, v in carrier_scores.items() if v > 0}
    if nonzero:
        print(f"[SpecMatcher] All scores: {nonzero}")

    # ── Country detection ──
    dest_country = parsed_label.get("destination_country", "") or parsed_label.get("country_code", "")

    if not dest_country:
        for t in texts:
            upper = t.upper().strip()
            if upper in COUNTRY_NAMES_TO_CODE:
                dest_country = COUNTRY_NAMES_TO_CODE[upper]

    origin_country = ""
    sender = parsed_label.get("sender_address", "") or parsed_label.get("ship_from_address", "")
    if sender:
        parts = sender.split("|") if "|" in sender else [sender]
        for part in reversed(parts):
            upper = part.strip().upper()
            if upper in COUNTRY_NAMES_TO_CODE:
                origin_country = COUNTRY_NAMES_TO_CODE[upper]
                break
            if len(upper) == 2 and upper in COUNTRY_TO_REGION:
                origin_country = upper
                break

    signals.origin_country = origin_country
    signals.destination_country = dest_country
    signals.origin_region = COUNTRY_TO_REGION.get(origin_country, "")
    signals.destination_region = COUNTRY_TO_REGION.get(dest_country, "")

    if origin_country and dest_country:
        signals.is_international = origin_country != dest_country
        signals.is_domestic = origin_country == dest_country
    else:
        signals.is_international = True

    return signals


async def match_carrier_from_label(parsed_label: Dict, db) -> Dict:
    signals = extract_label_signals(parsed_label)

    print(f"[SpecMatcher] Signals: carrier={signals.carrier} "
          f"(confidence={signals.carrier_confidence:.0%}), "
          f"origin={signals.origin_country}({signals.origin_region}), "
          f"dest={signals.destination_country}({signals.destination_region}), "
          f"service={signals.service_type}")
    if signals.carrier_signals:
        print(f"[SpecMatcher] Evidence: {', '.join(signals.carrier_signals)}")

    all_carriers = await db.carriers.find(
        {}, {"_id": 1, "carrier": 1}
    ).to_list(length=None)

    for c in all_carriers:
        c["_id"] = str(c["_id"])

    if not all_carriers:
        return {
            "signals": _signals_to_dict(signals),
            "best_match": None,
            "alternatives": [],
            "all_carriers": [],
            "needs_confirmation": True,
            "message": "No carriers configured. Upload a carrier specification first.",
        }

    scored = []
    for carrier_doc in all_carriers:
        score, reasons = _score_carrier(carrier_doc, signals)
        match = CarrierMatch(
            carrier_id=carrier_doc["_id"],
            carrier_name=carrier_doc["carrier"],
            spec_name=carrier_doc["carrier"],
            confidence=score,
            match_reasons=reasons,
        )
        scored.append(match)

    scored.sort(key=lambda m: m.confidence, reverse=True)
    best = scored[0] if scored and scored[0].confidence > 0 else None
    alternatives = [s for s in scored[1:5] if s.confidence > 0]

    if best:
        best.is_best_match = True

    needs_confirmation = True
    if not best:
        message = (f"Could not auto-detect carrier. "
                   f"Detected type: '{signals.carrier or 'unknown'}'. "
                   f"Please select manually.")
    elif best.confidence >= 0.8:
        message = (f"Auto-detected: '{best.carrier_name}' "
                   f"(confidence: {best.confidence:.0%}). "
                   f"{', '.join(best.match_reasons[:3])}.")
    elif best.confidence >= 0.4:
        message = (f"Best guess: '{best.carrier_name}' "
                   f"(confidence: {best.confidence:.0%}). "
                   f"Please verify.")
    else:
        message = (f"Low confidence: '{best.carrier_name}' "
                   f"({best.confidence:.0%}). Please select manually.")

    return {
        "signals": _signals_to_dict(signals),
        "best_match": best.to_dict() if best else None,
        "alternatives": [a.to_dict() for a in alternatives],
        "all_carriers": [{"_id": c["_id"], "carrier": c["carrier"]} for c in all_carriers],
        "needs_confirmation": needs_confirmation,
        "message": message,
    }


def _score_carrier(carrier_doc: Dict, signals: LabelSignals) -> Tuple[float, List[str]]:
    """Score how well a DB carrier matches the label signals."""
    score = 0.0
    reasons = []
    carrier_name = carrier_doc.get("carrier", "").lower().strip()
    detected = signals.carrier.lower().strip()

    if not detected:
        return 0.1, ["carrier not detected from label"]

    if detected in carrier_name or carrier_name.startswith(detected):
        score = signals.carrier_confidence * 0.7
        reasons.append(f"carrier '{detected}' matches '{carrier_name}'")
    elif carrier_name in detected:
        score = signals.carrier_confidence * 0.5
        reasons.append(f"carrier partial match: '{carrier_name}' in '{detected}'")
    else:
        return 0.0, [f"mismatch: detected '{detected}', DB has '{carrier_name}'"]

    carrier_name_parts = carrier_name.split()
    if signals.origin_region:
        if signals.origin_region in carrier_name:
            score += 0.15
            reasons.append(f"origin region '{signals.origin_region}' in spec name")
        elif any(r in carrier_name for r in ["international", "worldwide", "global"]):
            score += 0.05
            reasons.append("spec is international/worldwide")

    if signals.service_type and detected in signals.service_type.lower():
        score += 0.10
        reasons.append(f"service '{signals.service_type}' confirms carrier")

    if signals.is_international:
        score += 0.05
        reasons.append("international shipment")

    score = min(score, 1.0)
    return round(score, 3), reasons


def _signals_to_dict(signals: LabelSignals) -> Dict:
    return {
        "carrier": signals.carrier,
        "carrier_confidence": signals.carrier_confidence,
        "carrier_signals": signals.carrier_signals,
        "origin_country": signals.origin_country,
        "destination_country": signals.destination_country,
        "origin_region": signals.origin_region,
        "destination_region": signals.destination_region,
        "service_type": signals.service_type,
        "tracking_number": signals.tracking_number,
        "is_international": signals.is_international,
        "is_domestic": signals.is_domestic,
    }


# ═══════════════════════════════════════════════════════════════
# EDI SIGNAL EXTRACTION
# ═══════════════════════════════════════════════════════════════

def extract_edi_signals(edi_content: str) -> Dict:
    signals = {"carrier": "", "format_type": "", "sender": "", "receiver": ""}
    content = edi_content.strip()
    if content.startswith("{") or content.startswith("["):
        signals["format_type"] = "json"
    elif content.startswith("<"):
        signals["format_type"] = "xml"
    elif "~" in content and "*" in content:
        signals["format_type"] = "x12"
    elif "'" in content and "+" in content:
        signals["format_type"] = "edifact"
    else:
        signals["format_type"] = "unknown"

    content_upper = content.upper()
    carrier_keywords = {
        "ups": ["UPS", "UNITED PARCEL"],
        "dhl": ["DHL", "DEUTSCHE POST"],
        "fedex": ["FEDEX", "FEDERAL EXPRESS"],
        "tnt": ["TNT"],
    }
    for carrier, keywords in carrier_keywords.items():
        for kw in keywords:
            if kw in content_upper:
                signals["carrier"] = carrier
                break
        if signals["carrier"]:
            break

    if signals["format_type"] == "x12":
        isa_match = re.search(r"ISA\*[^~]*", content)
        if isa_match:
            parts = isa_match.group(0).split("*")
            if len(parts) >= 9:
                signals["sender"] = parts[6].strip()
                signals["receiver"] = parts[8].strip()

    return signals


async def match_carrier_from_edi(edi_content: str, db) -> Dict:
    edi_signals = extract_edi_signals(edi_content)
    all_carriers = await db.carriers.find(
        {}, {"_id": 1, "carrier": 1}
    ).to_list(length=None)
    for c in all_carriers:
        c["_id"] = str(c["_id"])
    if not all_carriers:
        return {
            "signals": edi_signals, "best_match": None, "alternatives": [],
            "all_carriers": [], "needs_confirmation": True,
            "message": "No carriers configured.",
        }
    detected = edi_signals.get("carrier", "").lower()
    scored = []
    for carrier_doc in all_carriers:
        name = carrier_doc.get("carrier", "").lower()
        if detected and (detected in name or name.startswith(detected)):
            score, reasons = 0.7, [f"'{detected}' found in EDI"]
        elif detected:
            score, reasons = 0.0, ["mismatch"]
        else:
            score, reasons = 0.1, ["not detected"]
        scored.append(CarrierMatch(
            carrier_id=carrier_doc["_id"], carrier_name=carrier_doc["carrier"],
            spec_name=carrier_doc["carrier"], confidence=score,
            match_reasons=reasons,
        ))
    scored.sort(key=lambda m: m.confidence, reverse=True)
    best = scored[0] if scored and scored[0].confidence > 0 else None
    if best:
        best.is_best_match = True
    return {
        "signals": edi_signals,
        "best_match": best.to_dict() if best else None,
        "alternatives": [a.to_dict() for a in scored[1:5] if a.confidence > 0],
        "all_carriers": [{"_id": c["_id"], "carrier": c["carrier"]} for c in all_carriers],
        "needs_confirmation": True,
        "message": f"Detected: '{detected or 'unknown'}'. Format: {edi_signals.get('format_type')}.",
    }