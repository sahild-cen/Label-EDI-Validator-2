"""
Spec Matcher - Auto-detect carrier and spec from label content
==============================================================

New flow (label-first, no carrier dropdown):
1. Parse the label → extract carrier signals (tracking format, service type, etc.)
2. Search MongoDB carriers collection for matching carrier(s)
3. If carrier has multiple spec versions/regions, score and rank them
4. Return best match + alternatives for user confirmation
5. If no match → return all available carriers for manual selection

Works with any carrier — detection is based on patterns in the label data.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict


# ═══════════════════════════════════════════════════════════════
# REGION DETECTION
# ═══════════════════════════════════════════════════════════════

COUNTRY_TO_REGION = {
    # Europe
    "DE": "europe", "FR": "europe", "GB": "europe", "UK": "europe",
    "NL": "europe", "BE": "europe", "AT": "europe", "CH": "europe",
    "IT": "europe", "ES": "europe", "PT": "europe", "PL": "europe",
    "SE": "europe", "DK": "europe", "NO": "europe", "FI": "europe",
    "IE": "europe", "CZ": "europe", "HU": "europe", "RO": "europe",
    "BG": "europe", "HR": "europe", "SK": "europe", "SI": "europe",
    "EE": "europe", "LV": "europe", "LT": "europe", "LU": "europe",
    "GR": "europe", "RS": "europe",
    # Americas
    "US": "us", "CA": "canada", "MX": "americas", "BR": "americas",
    "AR": "americas", "CL": "americas", "CO": "americas",
    # Asia Pacific
    "CN": "asia", "JP": "asia", "KR": "asia", "IN": "asia",
    "SG": "asia", "AU": "asia_pacific", "NZ": "asia_pacific",
    "TH": "asia", "MY": "asia", "ID": "asia", "PH": "asia",
    "VN": "asia", "TW": "asia", "HK": "asia",
    # Middle East / Africa
    "AE": "middle_east", "SA": "middle_east", "IL": "middle_east",
    "ZA": "africa", "NG": "africa", "KE": "africa", "EG": "middle_east",
}

# Carrier detection patterns from tracking numbers and label content
CARRIER_PATTERNS = {
    "ups": {
        "tracking_prefix": [r"^1Z"],
        "label_keywords": ["ups", "ups standard", "ups express", "ups saver", "ups ground",
                           "ups expedited", "ups worldwide", "united parcel service"],
    },
    "dhl": {
        "tracking_prefix": [r"^JD", r"^JJD", r"^\d{10}$"],
        "label_keywords": ["dhl", "dhl express", "dhl europack", "dhl parcel",
                        "dhl europremium", "deutsche post",
                        "express worldwide", "waybill",  # DHL product names without "DHL" prefix
                        "express 12:00", "express 9:00", "express easy"],
        "routing_patterns": [r"2L[A-Z]{2}"],  # DHL routing barcode
        "product_codes": ["ECX", "WPX", "EPL", "DOX", "TDT", "DOC", "ESI", "ESU"],  # DHL product content codes
    },
    "fedex": {
        "tracking_prefix": [r"^\d{12}$", r"^\d{15}$", r"^\d{20}$", r"^\d{22}$"],
        "label_keywords": ["fedex", "federal express", "fedex express", "fedex ground",
                           "fedex home delivery", "fedex freight"],
    },
    "tnt": {
        "tracking_prefix": [r"^GE\d{9}"],
        "label_keywords": ["tnt", "tnt express"],
    },
    "dpd": {
        "tracking_prefix": [r"^0\d{13}$"],
        "label_keywords": ["dpd", "dpd group", "dpd classic", "dpd express"],
    },
    "gls": {
        "tracking_prefix": [],
        "label_keywords": ["gls", "general logistics"],
    },
}


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class LabelSignals:
    carrier: str = ""
    origin_country: str = ""
    destination_country: str = ""
    origin_region: str = ""
    destination_region: str = ""
    service_type: str = ""
    tracking_number: str = ""
    is_international: bool = False
    is_domestic: bool = False


@dataclass
class CarrierMatch:
    carrier_id: str             # MongoDB _id
    carrier_name: str           # e.g., "UPS"
    spec_name: str              # User-given name or carrier name
    confidence: float           # 0.0 - 1.0
    match_reasons: List[str]    # Why this was matched
    is_best_match: bool = False

    def to_dict(self):
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# SIGNAL EXTRACTION FROM LABEL
# ═══════════════════════════════════════════════════════════════

def extract_label_signals(parsed_label: Dict) -> LabelSignals:
    """Extract carrier/region signals from a parsed label (output of zpl_parser)."""
    signals = LabelSignals()

    # --- Tracking number → carrier detection ---
    tracking = parsed_label.get("tracking_number", "")
    signals.tracking_number = tracking

    for carrier, patterns in CARRIER_PATTERNS.items():
        for prefix_pattern in patterns.get("tracking_prefix", []):
            if re.match(prefix_pattern, tracking):
                signals.carrier = carrier
                break
        if signals.carrier:
            break

    # --- Label text → carrier detection (fallback) ---
    if not signals.carrier:
        service = parsed_label.get("service_type", "").lower()
        all_text = " ".join(str(v) for v in parsed_label.values()).lower()

        for carrier, patterns in CARRIER_PATTERNS.items():
            for kw in patterns.get("label_keywords", []):
                if kw in service or kw in all_text:
                    signals.carrier = carrier
                    break
            if signals.carrier:
                break

    # --- Country detection ---
    dest_country = parsed_label.get("country_code", "")
    origin_country = ""

    # Extract origin country from sender address
    sender = parsed_label.get("sender_address", "") or parsed_label.get("ship_from_address", "")
    if sender:
        country_name_map = {
            "NETHERLANDS": "NL", "GERMANY": "DE", "FRANCE": "FR",
            "SPAIN": "ES", "ITALY": "IT", "BELGIUM": "BE",
            "UNITED KINGDOM": "GB", "SWEDEN": "SE", "AUSTRIA": "AT",
            "SWITZERLAND": "CH", "POLAND": "PL", "DENMARK": "DK",
            "UNITED STATES": "US", "USA": "US", "CANADA": "CA",
            "AUSTRALIA": "AU", "JAPAN": "JP", "CHINA": "CN",
            "INDIA": "IN", "BRAZIL": "BR", "MEXICO": "MX",
            "SINGAPORE": "SG", "PORTUGAL": "PT", "IRELAND": "IE",
            "NORWAY": "NO", "FINLAND": "FI",
        }
        parts = sender.split("|")
        for part in reversed(parts):
            part_upper = part.strip().upper()
            if len(part_upper) == 2 and part_upper in COUNTRY_TO_REGION:
                origin_country = part_upper
                break
            if part_upper in country_name_map:
                origin_country = country_name_map[part_upper]
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

    signals.service_type = parsed_label.get("service_type", "")

    return signals


# ═══════════════════════════════════════════════════════════════
# CARRIER MATCHING (searches MongoDB)
# ═══════════════════════════════════════════════════════════════

async def match_carrier_from_label(parsed_label: Dict, db) -> Dict:
    """
    Main entry point: parse label signals, search MongoDB carriers,
    return best match + alternatives.

    Returns:
    {
        "signals": { carrier, origin, destination, ... },
        "best_match": { carrier_id, carrier_name, confidence, reasons, ... } | null,
        "alternatives": [ ... ],
        "all_carriers": [ {_id, carrier} ... ],  # for manual dropdown
        "needs_confirmation": true/false,
        "message": "..."
    }
    """
    # Step 1: Extract signals
    signals = extract_label_signals(parsed_label)
    print(f"[SpecMatcher] Signals: carrier={signals.carrier}, "
          f"origin={signals.origin_country}({signals.origin_region}), "
          f"dest={signals.destination_country}({signals.destination_region}), "
          f"service={signals.service_type}")

    # Step 2: Get all carriers from DB
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
            "message": "No carriers configured yet. Please upload a carrier specification first.",
        }

    # Step 3: Score each carrier
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

    # Sort by confidence
    scored.sort(key=lambda m: m.confidence, reverse=True)

    best = scored[0] if scored and scored[0].confidence > 0 else None
    alternatives = [s for s in scored[1:5] if s.confidence > 0]

    if best:
        best.is_best_match = True

    # Build response
    needs_confirmation = True
    if not best:
        message = (f"Could not auto-detect a matching carrier. "
                   f"Detected carrier type: '{signals.carrier or 'unknown'}'. "
                   f"Please select the correct carrier manually.")
    elif best.confidence >= 0.8:
        message = (f"Auto-detected: '{best.carrier_name}' "
                   f"(confidence: {best.confidence:.0%}). "
                   f"{', '.join(best.match_reasons)}. "
                   f"Please confirm this is correct.")
    elif best.confidence >= 0.4:
        message = (f"Best guess: '{best.carrier_name}' "
                   f"(confidence: {best.confidence:.0%}). "
                   f"Please verify this is the correct carrier.")
    else:
        message = (f"Low confidence match: '{best.carrier_name}' "
                   f"(confidence: {best.confidence:.0%}). "
                   f"Please select the correct carrier.")

    return {
        "signals": _signals_to_dict(signals),
        "best_match": best.to_dict() if best else None,
        "alternatives": [a.to_dict() for a in alternatives],
        "all_carriers": [{"_id": c["_id"], "carrier": c["carrier"]} for c in all_carriers],
        "needs_confirmation": needs_confirmation,
        "message": message,
    }


def _score_carrier(carrier_doc: Dict, signals: LabelSignals) -> Tuple[float, List[str]]:
    """
    Score how well a carrier in the DB matches the label signals.

    Scoring:
    - Carrier name exact match:     +0.60
    - Carrier name partial match:   +0.40
    - Service type contains carrier:+0.20
    - Region info available:        +0.10
    - International detected:       +0.10
    """
    score = 0.0
    reasons = []
    carrier_name = carrier_doc.get("carrier", "").lower().strip()
    detected_carrier = signals.carrier.lower().strip()

    if not detected_carrier:
        # Can't detect carrier from label — low confidence for all
        return 0.1, ["carrier not detected from label"]

    # Exact carrier match
    if detected_carrier == carrier_name:
        score += 0.60
        reasons.append(f"carrier '{detected_carrier}' matches")
    # Partial match (e.g., detected "ups" and DB has "UPS Express Europe")
    elif detected_carrier in carrier_name or carrier_name in detected_carrier:
        score += 0.40
        reasons.append(f"carrier '{detected_carrier}' partial match with '{carrier_name}'")
    else:
        # No carrier match at all
        return 0.0, [f"carrier mismatch: detected '{detected_carrier}', DB has '{carrier_name}'"]

    # Service type boost
    if signals.service_type:
        service_lower = signals.service_type.lower()
        if detected_carrier in service_lower:
            score += 0.15
            reasons.append(f"service '{signals.service_type}' confirms carrier")

    # Region info boost
    if signals.origin_region:
        score += 0.05
        reasons.append(f"origin: {signals.origin_country} ({signals.origin_region})")
    if signals.destination_region:
        score += 0.05
        reasons.append(f"destination: {signals.destination_country} ({signals.destination_region})")

    # International shipment detected
    if signals.is_international:
        score += 0.05
        reasons.append("international shipment")

    # Tracking number present
    if signals.tracking_number:
        score += 0.10
        reasons.append(f"tracking: {signals.tracking_number[:10]}...")

    score = min(score, 1.0)
    return round(score, 3), reasons


def _signals_to_dict(signals: LabelSignals) -> Dict:
    return {
        "carrier": signals.carrier,
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
    """
    Extract carrier signals from EDI content.
    Works with X12, EDIFACT, JSON, and XML formats.
    """
    signals = {
        "carrier": "",
        "format_type": "",
        "sender": "",
        "receiver": "",
    }

    content = edi_content.strip()

    # Detect format
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

    # Detect carrier from content
    for carrier, patterns in CARRIER_PATTERNS.items():
        for kw in patterns.get("label_keywords", []):
            if kw.upper() in content_upper:
                signals["carrier"] = carrier
                break
        if signals["carrier"]:
            break

    # Extract sender/receiver from X12 ISA segment
    if signals["format_type"] == "x12":
        isa_match = re.search(r"ISA\*[^~]*", content)
        if isa_match:
            parts = isa_match.group(0).split("*")
            if len(parts) >= 9:
                signals["sender"] = parts[6].strip()
                signals["receiver"] = parts[8].strip()

    return signals


async def match_carrier_from_edi(edi_content: str, db) -> Dict:
    """
    Auto-detect carrier from EDI content and match against DB.
    Same return format as match_carrier_from_label.
    """
    edi_signals = extract_edi_signals(edi_content)

    # Get all carriers
    all_carriers = await db.carriers.find(
        {}, {"_id": 1, "carrier": 1}
    ).to_list(length=None)

    for c in all_carriers:
        c["_id"] = str(c["_id"])

    if not all_carriers:
        return {
            "signals": edi_signals,
            "best_match": None,
            "alternatives": [],
            "all_carriers": [],
            "needs_confirmation": True,
            "message": "No carriers configured. Upload a carrier specification first.",
        }

    detected = edi_signals.get("carrier", "").lower()

    scored = []
    for carrier_doc in all_carriers:
        carrier_name = carrier_doc.get("carrier", "").lower()
        if detected and (detected == carrier_name or detected in carrier_name):
            score = 0.7
            reasons = [f"carrier '{detected}' detected in EDI content"]
        elif detected:
            score = 0.0
            reasons = ["carrier mismatch"]
        else:
            score = 0.1
            reasons = ["carrier not detected from EDI"]

        scored.append(CarrierMatch(
            carrier_id=carrier_doc["_id"],
            carrier_name=carrier_doc["carrier"],
            spec_name=carrier_doc["carrier"],
            confidence=score,
            match_reasons=reasons,
        ))

    scored.sort(key=lambda m: m.confidence, reverse=True)
    best = scored[0] if scored and scored[0].confidence > 0 else None
    alternatives = [s for s in scored[1:5] if s.confidence > 0]

    if best:
        best.is_best_match = True

    return {
        "signals": edi_signals,
        "best_match": best.to_dict() if best else None,
        "alternatives": [a.to_dict() for a in alternatives],
        "all_carriers": [{"_id": c["_id"], "carrier": c["carrier"]} for c in all_carriers],
        "needs_confirmation": True,
        "message": f"Detected carrier: '{detected or 'unknown'}'. Format: {edi_signals.get('format_type', 'unknown')}.",
    }