"""
Rule Canonicalizer - Field Name Normalization & Regex Correction
================================================================
Maps variant field names to canonical names and fixes known bad regexes.

NEW: Supports a corrections/learning database. When a validation failure is
marked as a false positive, the correction is stored and used to:
1. Auto-add field name aliases
2. Override bad regexes for specific carrier+field combos
3. Feed few-shot examples into the extraction prompt
"""

import re
from typing import List, Dict, Optional

# ═══════════════════════════════════════════════════════════════
# CANONICAL FIELD MAPPING
# ═══════════════════════════════════════════════════════════════

CANONICAL_FIELDS = {
    "tracking_number": [
        "tracking_number", "shipment_number", "shipment_identifier",
        "waybill_number", "consignment_number", "airwaybill_number",
        "awb_number", "air_waybill", "tracking_id", "package_tracking",
        "1z_tracking_number", "ups_tracking_number",
        "dhl_tracking_number", "fedex_tracking_number",
    ],
    "postal_code": [
        "postal_code", "postcode", "postcode_town",
        "zip_code", "zipcode", "post_code",
        "ship_to_postal_code", "destination_postal_code",
        "receiver_postal_code", "delivery_postal_code",
        "receiver_postcode", "destination_postcode",
    ],
    "routing_barcode": [
        "routing_barcode", "routing_information_bar_code",
        "routing_label_barcode", "routing_code", "sort_code",
        "ups_routing_code", "urc",
    ],
    "license_plate": [
        "license_plate", "licence_plate", "licence_plate_identifier",
        "license_plate_barcode", "sscc", "sscc_barcode",
        "sscc_number", "serial_shipping_container_code",
    ],
    "barcode": [
        "barcode", "linear_barcode", "awb_barcode",
        "label_barcode", "main_barcode", "tracking_barcode",
        "tracking_number_barcode",
    ],
    "weight": [
        "weight", "gross_weight", "actual_weight",
        "package_weight", "shipment_weight", "total_weight",
        "declared_weight", "net_weight",
    ],
    "sender_name": [
        "sender_name", "shipper_name", "from_name", "origin_name",
        "ship_from_name", "consignor_name",
    ],
    "sender_address": [
        "sender_address", "shipper_address", "from_address", "origin_address",
        "ship_from_address", "ship_from", "from_address_block",
        "shipper_address_block", "sender_address_block",
        "consignor_address", "origin_address_block",
    ],
    "receiver_name": [
        "receiver_name", "recipient_name", "to_name",
        "destination_name", "consignee_name",
        "ship_to_name", "delivery_name",
    ],
    "receiver_address": [
        "receiver_address", "recipient_address", "to_address",
        "destination_address", "consignee_address",
        "ship_to_address", "ship_to", "delivery_address",
        "ship_to_address_block", "consignee_address_block",
    ],
    "country_code": [
        "country_code", "country", "destination_country",
        "origin_country", "iso_country_code",
        "ship_to_country", "receiver_country",
        "delivery_country", "destination_country_code",
    ],
    "city": [
        "city", "ship_to_city", "destination_city",
        "receiver_city", "delivery_city", "town",
    ],
    "service_type": [
        "service_type", "service_code", "product_code",
        "service_indicator", "delivery_service",
        "product", "product_type", "product_name",
        "service_name", "service_level", "ups_service",
        "dhl_product", "fedex_service",
    ],
    "reference_number": [
        "reference_number", "reference", "customer_reference",
        "ref_number", "order_reference", "shipper_reference",
        "po_number", "purchase_order",
    ],
    "piece_count": [
        "piece_count", "pieces", "number_of_pieces",
        "total_pieces", "package_count", "package_number",
        "number_of_packages",
    ],
    "label_dimensions": [
        "label_dimensions", "label_width", "label_length",
        "label_height", "label_size",
    ],
}

# Build a fast reverse lookup: variant -> canonical
_ALIAS_LOOKUP = {}
for canonical, variants in CANONICAL_FIELDS.items():
    for v in variants:
        _ALIAS_LOOKUP[v] = canonical


# ═══════════════════════════════════════════════════════════════
# CARRIER-SPECIFIC REGEX CORRECTIONS
# ═══════════════════════════════════════════════════════════════

CARRIER_REGEX_CORRECTIONS = {
    "tracking_number": {
        "ups": r"^1Z[A-Z0-9]{16}$",
        "dhl": r"^[A-Z0-9]{10,39}$",
        "fedex": r"^\d{12,22}$",
        "default": r"^[A-Z0-9]{8,35}$",
    },
    "postal_code": {
        "default": r"^[A-Z0-9 \-]{3,10}$",
    },
    "country_code": {
        "default": r"^[A-Z]{2,3}$",
    },
    "weight": {
        "default": r"^\d+(\.\d+)?\s*(KG|LBS?)$",
    },
}


# ═══════════════════════════════════════════════════════════════
# LEARNED CORRECTIONS DATABASE INTERFACE
# ═══════════════════════════════════════════════════════════════

# In-memory cache of learned corrections (loaded from MongoDB at startup)
_learned_aliases: Dict[str, str] = {}       # field_variant -> canonical
_learned_regexes: Dict[str, Dict] = {}      # canonical_field -> {carrier -> regex}
_golden_rules: Dict[str, List[Dict]] = {}   # carrier -> list of verified rules


def load_learned_corrections(db=None):
    """
    Load learned corrections from MongoDB.
    Call this at app startup.

    Collections used:
    - learned_aliases: {variant: str, canonical: str}
    - learned_regexes: {field: str, carrier: str, regex: str}
    - golden_rules: {carrier: str, rules: [...]}
    """
    global _learned_aliases, _learned_regexes, _golden_rules

    if db is None:
        return

    try:
        # Load aliases
        for doc in db.learned_aliases.find():
            _learned_aliases[doc["variant"]] = doc["canonical"]
            # Also add to CANONICAL_FIELDS for consistency
            canonical = doc["canonical"]
            if canonical in CANONICAL_FIELDS:
                if doc["variant"] not in CANONICAL_FIELDS[canonical]:
                    CANONICAL_FIELDS[canonical].append(doc["variant"])
                _ALIAS_LOOKUP[doc["variant"]] = canonical

        # Load regex corrections
        for doc in db.learned_regexes.find():
            field = doc["field"]
            carrier = doc.get("carrier", "default")
            if field not in _learned_regexes:
                _learned_regexes[field] = {}
            _learned_regexes[field][carrier] = doc["regex"]

        # Load golden rules
        for doc in db.golden_rules.find():
            carrier = doc["carrier"].lower()
            _golden_rules[carrier] = doc.get("rules", [])

        print(f"[Canonicalizer] Loaded {len(_learned_aliases)} aliases, "
              f"{sum(len(v) for v in _learned_regexes.values())} regex corrections, "
              f"{len(_golden_rules)} carrier golden rule sets")

    except Exception as e:
        print(f"[Canonicalizer] Warning: could not load learned corrections: {e}")


def save_alias_correction(db, variant: str, canonical: str):
    """Save a newly learned field name alias to MongoDB."""
    if db is None:
        return
    try:
        db.learned_aliases.update_one(
            {"variant": variant},
            {"$set": {"variant": variant, "canonical": canonical}},
            upsert=True
        )
        _learned_aliases[variant] = canonical
        _ALIAS_LOOKUP[variant] = canonical
        if canonical in CANONICAL_FIELDS and variant not in CANONICAL_FIELDS[canonical]:
            CANONICAL_FIELDS[canonical].append(variant)
        print(f"[Canonicalizer] Learned alias: '{variant}' -> '{canonical}'")
    except Exception as e:
        print(f"[Canonicalizer] Warning: could not save alias: {e}")


def save_regex_correction(db, field: str, carrier: str, regex: str):
    """Save a learned regex correction to MongoDB."""
    if db is None:
        return
    try:
        db.learned_regexes.update_one(
            {"field": field, "carrier": carrier},
            {"$set": {"field": field, "carrier": carrier, "regex": regex}},
            upsert=True
        )
        if field not in _learned_regexes:
            _learned_regexes[field] = {}
        _learned_regexes[field][carrier] = regex
        print(f"[Canonicalizer] Learned regex: '{field}' ({carrier}) -> '{regex}'")
    except Exception as e:
        print(f"[Canonicalizer] Warning: could not save regex correction: {e}")


def save_golden_rules(db, carrier: str, rules: List[Dict]):
    """Save verified golden rules for a carrier."""
    if db is None:
        return
    try:
        db.golden_rules.update_one(
            {"carrier": carrier.lower()},
            {"$set": {"carrier": carrier.lower(), "rules": rules}},
            upsert=True
        )
        _golden_rules[carrier.lower()] = rules
        print(f"[Canonicalizer] Saved {len(rules)} golden rules for '{carrier}'")
    except Exception as e:
        print(f"[Canonicalizer] Warning: could not save golden rules: {e}")


def get_golden_rules(carrier: str) -> Optional[List[Dict]]:
    """Get verified golden rules for a carrier. Returns None if none saved."""
    return _golden_rules.get(carrier.lower())


# ═══════════════════════════════════════════════════════════════
# MAIN CANONICALIZATION FUNCTION
# ═══════════════════════════════════════════════════════════════

def canonicalize_rules(rules: List[Dict], carrier_name: str = "") -> List[Dict]:
    """
    Normalize field names to canonical form and fix known bad regexes.

    Uses three layers of knowledge:
    1. Static CANONICAL_FIELDS mapping
    2. Learned aliases from corrections database
    3. Carrier-specific regex corrections (static + learned)
    """
    canonical_rules = []
    carrier_key = carrier_name.lower().strip() if carrier_name else ""

    for rule in rules:
        field = rule.get("field", "").lower().strip()
        # Normalize underscores/hyphens/spaces
        field = re.sub(r"[\s\-]+", "_", field)
        canonical_field = field

        # Step 1: Look up in static + learned aliases
        if field in _ALIAS_LOOKUP:
            canonical_field = _ALIAS_LOOKUP[field]
        elif field in _learned_aliases:
            canonical_field = _learned_aliases[field]
        else:
            # Fuzzy: try removing common prefixes/suffixes
            for prefix in ["ship_to_", "ship_from_", "destination_", "origin_", "receiver_", "sender_"]:
                stripped = field.replace(prefix, "")
                if stripped in _ALIAS_LOOKUP:
                    canonical_field = _ALIAS_LOOKUP[stripped]
                    break

        if canonical_field != field:
            print(f"  [Canonicalizer] '{field}' -> '{canonical_field}'")

        rule["field"] = canonical_field

        # Step 2: Fix known bad regexes
        rule = _fix_regex(rule, canonical_field, carrier_key)

        canonical_rules.append(rule)

    return canonical_rules


def _fix_regex(rule: Dict, canonical_field: str, carrier_key: str) -> Dict:
    """
    If the current regex on a rule looks wrong, replace it with the
    known-correct pattern from static corrections or learned corrections.
    """
    current_regex = rule.get("regex", "")

    # Check learned corrections first (they take priority)
    if canonical_field in _learned_regexes:
        learned = _learned_regexes[canonical_field]
        correct = learned.get(carrier_key) or learned.get("default")
        if correct and current_regex and _regex_looks_wrong(current_regex, canonical_field):
            print(f"  [Canonicalizer] Learned regex fix: '{canonical_field}' '{current_regex}' -> '{correct}'")
            rule["regex"] = correct
            return rule

    # Then static corrections
    corrections = CARRIER_REGEX_CORRECTIONS.get(canonical_field)
    if not corrections:
        return rule

    correct_regex = corrections.get(carrier_key) or corrections.get("default")
    if not correct_regex:
        return rule

    if current_regex and _regex_looks_wrong(current_regex, canonical_field):
        print(f"  [Canonicalizer] Static regex fix: '{canonical_field}' '{current_regex}' -> '{correct_regex}'")
        rule["regex"] = correct_regex

    return rule


def _regex_looks_wrong(regex: str, canonical_field: str) -> bool:
    """
    Heuristic: detect obviously wrong regexes for common field types.
    """
    try:
        re.compile(regex)
    except re.error:
        return True

    # Tracking numbers: max length below 10 is wrong
    if canonical_field == "tracking_number":
        range_quants = re.findall(r"\{(\d+),(\d+)\}", regex)
        for min_v, max_v in range_quants:
            if int(max_v) < 10:
                return True
        single_quants = re.findall(r"(?<!\{)\{(\d+)\}(?!,)", regex)
        for val in single_quants:
            if int(val) < 10:
                return True

    # Postal codes: exact 5-digit only is too restrictive
    if canonical_field == "postal_code":
        if regex in (r"^[A-Za-z0-9]{5}$", r"^\d{5}$"):
            return True

    # Country code: anything longer than 3 chars is wrong
    if canonical_field == "country_code":
        range_quants = re.findall(r"\{(\d+),(\d+)\}", regex)
        for min_v, max_v in range_quants:
            if int(max_v) > 5:
                return True

    return False