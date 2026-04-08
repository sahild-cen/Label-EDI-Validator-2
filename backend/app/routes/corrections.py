"""
corrections.py — Place in app/routes/corrections.py

Two things this does:
1. When user says "this error is wrong" → stores it, suppresses it next time
2. When user says "you missed this check" → injects field directly into 
   carrier's active rules in MongoDB so it's checked immediately on revalidate
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import re

router = APIRouter()


# ═══════════════════════════════════════════
# Field name normalizer
# ═══════════════════════════════════════════

KNOWN_FIELDS = {
    "tracking_number": ["tracking number", "tracking no", "tracking #", "tracking", "trk", "waybill", "waybill number", "awb"],
    "shipment_date": ["shipment date", "ship date", "date", "pickup date", "dispatch date", "collection date", "shipping date"],
    "service_type": ["service type", "service", "service name", "service description", "product", "product type", "delivery service"],
    "service_description": ["service description", "service desc"],
    "sender_address": ["sender address", "ship from", "shipper address", "from address", "origin address", "sender"],
    "receiver_address": ["receiver address", "ship to address", "recipient address", "to address", "destination address", "consignee address"],
    "sender_name": ["sender name", "shipper name", "from name"],
    "receiver_name": ["receiver name", "recipient name", "to name", "consignee name"],
    "postal_code": ["postal code", "postcode", "zip code", "zip", "destination postal code", "destination zip"],
    "city": ["city", "destination city", "ship to city", "town"],
    "country_code": ["country code", "country", "destination country"],
    "weight": ["weight", "package weight", "gross weight", "shipment weight", "actual weight"],
    "piece_count": ["piece count", "pieces", "package count", "number of pieces", "no of pieces", "package sequence"],
    "reference_number": ["reference number", "reference", "ref number", "ref", "customer reference"],
    "billing": ["billing", "billing method", "billing type", "payment method", "bill type"],
    "license_plate": ["license plate", "licence plate", "sscc", "lp"],
    "routing_barcode": ["routing barcode", "routing code", "sort code", "ursa code", "ursa"],
    "barcode": ["barcode", "tracking barcode", "1d barcode"],
    "goods_description": ["goods description", "description", "content", "contents", "desc"],
    "special_handling": ["special handling", "handling codes", "handling"],
    "destination_airport": ["destination airport", "airport", "airport id", "airport code"],
    "form_id": ["form id", "form code", "form number", "form"],
    "service_icon": ["service icon", "icon"],
    "maxicode": ["maxicode", "maxi code"],
    "postal_barcode": ["postal barcode"],
    "recipient_country_code": ["recipient country code", "country code with parentheses"],
    "opco_identifier": ["opco identifier", "opco", "company identifier"],
    "planned_service_label": ["planned service label", "planned service", "service level"],
    "documentation_indicator": ["documentation indicator", "doc indicator", "edi indicator"],
    "bill_type": ["bill type", "billing type"],
    "ursa_routing_code": ["ursa routing code", "ursa code", "ursa", "routing code"],
    "airport_id": ["airport id", "airport code", "destination airport"],
    "destination_zip": ["destination zip", "destination postal code", "dest zip"],
    "package_count": ["package count", "package sequence", "piece count", "pieces"],
}


def normalize_field_name(raw_input: str) -> str:
    """
    Convert user input like "Shipment Date" or "tracking number"
    into the canonical field name like "shipment_date" or "tracking_number".
    """
    cleaned = raw_input.strip().lower()

    # Already matches a canonical name?
    for canonical, aliases in KNOWN_FIELDS.items():
        if cleaned == canonical:
            return canonical
        if cleaned in aliases:
            return canonical

    # Try snake_case version
    snake = re.sub(r'[^a-z0-9]+', '_', cleaned).strip('_')
    for canonical, aliases in KNOWN_FIELDS.items():
        if snake == canonical:
            return canonical

    # Fuzzy: does cleaned contain a known alias or vice versa?
    best_match = None
    best_len = 0
    for canonical, aliases in KNOWN_FIELDS.items():
        for alias in aliases:
            if alias in cleaned or cleaned in alias:
                if len(alias) > best_len:
                    best_match = canonical
                    best_len = len(alias)
    if best_match:
        return best_match

    # Nothing matched — return snake_case of whatever they typed
    return snake


# ═══════════════════════════════════════════
# Models
# ═══════════════════════════════════════════

class CorrectionRequest(BaseModel):
    carrier: str
    field: str
    correction_type: str  # "wrong_error" or "missing_check"
    actual_value: Optional[str] = None
    notes: Optional[str] = None


# ═══════════════════════════════════════════
# POST /api/corrections
# ═══════════════════════════════════════════

@router.post("/api/corrections")
async def submit_correction(req: CorrectionRequest):
    from app.database import get_database
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    carrier = req.carrier.lower().strip()
    raw_field = req.field.strip()
    field = normalize_field_name(raw_field)

    if field != raw_field.lower().replace(" ", "_"):
        print(f"  [Normalizer] '{raw_field}' → '{field}'")

    # Audit trail
    db.validation_corrections.insert_one({
        "carrier": carrier,
        "field": field,
        "raw_input": raw_field,
        "correction_type": req.correction_type,
        "actual_value": req.actual_value,
        "notes": req.notes,
        "timestamp": datetime.utcnow(),
    })

    if req.correction_type == "wrong_error":
        db.false_positive_overrides.update_one(
            {"carrier": carrier, "field": field},
            {
                "$set": {
                    "carrier": carrier,
                    "field": field,
                    "actual_value": req.actual_value,
                    "updated_at": datetime.utcnow(),
                },
                "$inc": {"count": 1},
            },
            upsert=True,
        )
        return {
            "success": True,
            "message": f"Got it — '{field}' errors will be suppressed for {carrier} labels.",
            "normalized_field": field,
        }

    elif req.correction_type == "missing_check":
        # Save to mandatory_field_overrides (backup)
        db.mandatory_field_overrides.update_one(
            {"carrier": carrier, "field": field},
            {
                "$set": {
                    "carrier": carrier,
                    "field": field,
                    "required": True,
                    "pattern": None,
                    "description": req.notes or f"User reported: {field} should be checked",
                    "source": "user_feedback",
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )

        # ALSO inject directly into the carrier's active rules
        # This is the primary mechanism — works immediately on revalidate
        injected = _inject_field_into_active_rules(db, carrier, field, req.notes)

        if injected:
            return {
                "success": True,
                "message": f"'{field}' is now mandatory for {carrier}. "
                           f"Re-validate to see the updated results.",
                "normalized_field": field,
            }
        else:
            # Fallback: override collection will still work via _load_mandatory_overrides
            return {
                "success": True,
                "message": f"'{field}' override saved for {carrier}. "
                           f"It will be checked on next validation.",
                "normalized_field": field,
            }

    return {"success": False, "message": "Unknown correction type"}


# ═══════════════════════════════════════════
# Inject field into carrier's active rules
# ═══════════════════════════════════════════

def _inject_field_into_active_rules(db, carrier: str, field: str, notes: str = None) -> bool:
    """
    Write the missing field directly into the carrier's active rule version
    in the carriers collection. Uses case-insensitive carrier name matching.
    
    This means on revalidate, the field is part of the rules themselves —
    no separate collection lookup needed.
    """
    try:
        # Case-insensitive carrier lookup
        carrier_doc = db.carriers.find_one({
            "carrier": {"$regex": f"^{re.escape(carrier)}$", "$options": "i"}
        })

        if not carrier_doc:
            print(f"  [Missing Check] Carrier '{carrier}' not found in DB")
            return False

        rules_list = carrier_doc.get("rules", [])

        # Find active version index
        active_idx = None
        for i, rule_version in enumerate(rules_list):
            if rule_version.get("status") == "active":
                active_idx = i
                break

        if active_idx is None:
            print(f"  [Missing Check] No active rule version for '{carrier}'")
            return False

        active_rules = rules_list[active_idx]
        label_rules = active_rules.get("label_rules", {})
        field_formats = label_rules.get("field_formats", {})
        required_fields = label_rules.get("required_fields", [])

        # Already required? Nothing to do
        if field in field_formats and field_formats[field].get("required"):
            print(f"  [Missing Check] '{field}' already required for '{carrier}'")
            return True

        # Build the new field entry
        new_field = {
            "pattern": "",
            "required": True,
            "description": notes or f"User reported: {field} must be present on label",
        }

        # Add to required_fields list
        if field not in required_fields:
            required_fields.append(field)

        # Write to MongoDB
        db.carriers.update_one(
            {"_id": carrier_doc["_id"]},
            {
                "$set": {
                    f"rules.{active_idx}.label_rules.field_formats.{field}": new_field,
                    f"rules.{active_idx}.label_rules.required_fields": required_fields,
                }
            }
        )

        print(f"  [Missing Check] Injected '{field}' as required into "
              f"'{carrier}' active rules (v{active_rules.get('version', '?')})")
        return True

    except Exception as e:
        print(f"  [Missing Check] Error injecting into active rules: {e}")
        return False


# ═══════════════════════════════════════════
# GET /api/corrections
# ═══════════════════════════════════════════

@router.get("/api/corrections")
async def get_corrections(carrier: Optional[str] = None):
    from app.database import get_database
    db = get_database()
    if db is None:
        return {"corrections": []}

    query = {}
    if carrier:
        query["carrier"] = carrier.lower().strip()

    corrections = list(
        db.validation_corrections.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .limit(50)
    )
    return {"corrections": corrections}


# ═══════════════════════════════════════════
# Called by label_validator.py
# ═══════════════════════════════════════════

def check_corrections_before_failing(db, carrier: str, field: str) -> bool:
    """
    Returns True if this error should be SUPPRESSED.
    """
    if db is None:
        return False
    try:
        hit = db.false_positive_overrides.find_one({
            "carrier": carrier.lower().strip(),
            "field": field,
        })
        if hit:
            print(f"  [Learned] Suppressing '{field}' for {carrier} — "
                  f"flagged as incorrect ({hit.get('count', 1)}x)")
            return True
        return False
    except Exception:
        return False