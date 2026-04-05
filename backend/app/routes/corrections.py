"""
corrections.py — Place in app/routes/corrections.py

Add to main.py:
    from app.routes.corrections import router as corrections_router
    app.include_router(corrections_router)

Two things this does:
1. When user says "this error is wrong" → stores it, suppresses it next time
2. When user says "you missed this check" → stores it, enforces it next time
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
# Users type "Shipment Date" or "tracking number" or "PIECE COUNT"
# We need to convert that to "shipment_date", "tracking_number", "piece_count"
# AND match it to a known canonical name if possible.

# All known field names in the system — used for fuzzy matching
KNOWN_FIELDS = {
    # canonical_name: [possible user inputs]
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
    "piece_count": ["piece count", "pieces", "package count", "number of pieces", "no of pieces"],
    "reference_number": ["reference number", "reference", "ref number", "ref", "customer reference"],
    "billing": ["billing", "billing method", "billing type", "payment method", "bill type"],
    "license_plate": ["license plate", "licence plate", "sscc", "lp"],
    "routing_barcode": ["routing barcode", "routing code", "sort code", "ursa code", "ursa"],
    "barcode": ["barcode", "tracking barcode", "1d barcode"],
    "goods_description": ["goods description", "description", "content", "contents", "desc"],
    "special_handling": ["special handling", "handling codes", "handling"],
    "destination_airport": ["destination airport", "airport", "airport id", "airport code"],
    "form_id": ["form id", "form code", "form number", "form"],
}


def normalize_field_name(raw_input: str) -> str:
    """
    Convert user input like "Shipment Date" or "tracking number"
    into the canonical field name like "shipment_date" or "tracking_number".

    Steps:
    1. Clean: strip, lowercase
    2. Try exact match against known fields
    3. Try fuzzy match (input contains or is contained by a known alias)
    4. Fall back to snake_case conversion of the raw input
    """
    cleaned = raw_input.strip().lower()

    # Already in snake_case and matches a known field?
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

    # Nothing matched — just return snake_case of whatever they typed
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
# POST /api/corrections — User submits feedback
# ═══════════════════════════════════════════

@router.post("/api/corrections")
async def submit_correction(req: CorrectionRequest):
    from app.database import get_database
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    carrier = req.carrier.lower().strip()

    # Normalize whatever the user typed into a proper field name
    raw_field = req.field.strip()
    field = normalize_field_name(raw_field)

    if field != raw_field.lower().replace(" ", "_"):
        print(f"  [Normalizer] '{raw_field}' → '{field}'")

    # Store for audit
    db.validation_corrections.insert_one({
        "carrier": carrier,
        "field": field,
        "correction_type": req.correction_type,
        "actual_value": req.actual_value,
        "notes": req.notes,
        "timestamp": datetime.utcnow(),
    })

    if req.correction_type == "wrong_error":
        # "This error is wrong — the field IS correct on the label"
        # → Suppress this error in future validations
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
            "message": f"Got it — '{field}' errors will be suppressed for {carrier} labels going forward.",
            "normalized_field": field,
        }

    elif req.correction_type == "missing_check":
        # "You missed this — this field should be checked"
        # → Make it mandatory in future validations
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
        return {
            "success": True,
            "message": f"Got it — '{field}' is now mandatory for {carrier}. It will be checked in all future validations.",
            "normalized_field": field,
        }

    return {"success": False, "message": "Unknown correction type"}


# ═══════════════════════════════════════════
# GET /api/corrections — View past corrections
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
# Functions called by label_validator.py
# ═══════════════════════════════════════════

def check_corrections_before_failing(db, carrier: str, field: str) -> bool:
    """
    Called in label_validator.py BEFORE reporting a failure.
    Returns True if this error should be SUPPRESSED (user said it was wrong before).
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
                  f"previously flagged as incorrect ({hit.get('count', 1)}x)")
            return True
        return False
    except Exception:
        return False