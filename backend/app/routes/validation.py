import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.label_validator import LabelValidator
from app.services.edi_validator import EDIValidator
from app.services.zpl_parser import parse_zpl_script
from app.services.spec_matcher import (
    match_carrier_from_label,
    match_carrier_from_edi,
)
from app.utils.file_handler import save_upload_file, read_file_content, read_text_file
from app.database import get_database
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/api/validate", tags=["validation"])


# ═══════════════════════════════════════════════════════════════
# AUTO-DETECT ENDPOINTS (label-first flow)
# ═══════════════════════════════════════════════════════════════

@router.post("/detect-spec")
async def detect_spec(label_file: UploadFile = File(...)):
    """
    Parse a label file, auto-detect carrier + region,
    and return matched carrier from DB for user confirmation.

    Returns:
    {
        signals: { carrier, origin_country, destination_country, ... },
        best_match: { carrier_id, carrier_name, confidence, match_reasons, ... },
        alternatives: [ ... ],
        all_carriers: [ {_id, carrier}, ... ],  // for manual dropdown fallback
        needs_confirmation: true,
        message: "..."
    }
    """
    db = get_database()

    try:
        content = await label_file.read()
        script = content.decode("utf-8", errors="ignore")

        # Parse label with the spatial ZPL parser
        parsed_label = parse_zpl_script(script)

        if not parsed_label:
            # Still return all carriers for manual selection
            all_carriers = await db.carriers.find(
                {}, {"_id": 1, "carrier": 1}
            ).to_list(length=None)
            for c in all_carriers:
                c["_id"] = str(c["_id"])

            return {
                "signals": {},
                "best_match": None,
                "alternatives": [],
                "all_carriers": [{"_id": c["_id"], "carrier": c["carrier"]} for c in all_carriers],
                "needs_confirmation": True,
                "message": "Could not parse the label file. Please select a carrier manually."
            }

        # Match against carriers in MongoDB
        result = await match_carrier_from_label(parsed_label, db)
        return result

    except Exception as e:
        # On error, still return all carriers so user can pick manually
        try:
            all_carriers = await db.carriers.find(
                {}, {"_id": 1, "carrier": 1}
            ).to_list(length=None)
            for c in all_carriers:
                c["_id"] = str(c["_id"])
        except Exception:
            all_carriers = []

        return {
            "signals": {},
            "best_match": None,
            "alternatives": [],
            "all_carriers": [{"_id": c["_id"], "carrier": c["carrier"]} for c in all_carriers],
            "needs_confirmation": True,
            "message": f"Error analyzing label: {str(e)}. Please select a carrier manually."
        }


@router.post("/detect-edi-spec")
async def detect_edi_spec(edi_file: UploadFile = File(...)):
    """
    Parse an EDI file, auto-detect carrier,
    and return matched carrier from DB for user confirmation.
    """
    db = get_database()

    try:
        content = await edi_file.read()
        edi_text = content.decode("utf-8", errors="ignore")

        if not edi_text.strip():
            all_carriers = await db.carriers.find(
                {}, {"_id": 1, "carrier": 1}
            ).to_list(length=None)
            for c in all_carriers:
                c["_id"] = str(c["_id"])

            return {
                "signals": {},
                "best_match": None,
                "alternatives": [],
                "all_carriers": [{"_id": c["_id"], "carrier": c["carrier"]} for c in all_carriers],
                "needs_confirmation": True,
                "message": "EDI file is empty. Please select a carrier manually."
            }

        result = await match_carrier_from_edi(edi_text, db)
        return result

    except Exception as e:
        try:
            all_carriers = await db.carriers.find(
                {}, {"_id": 1, "carrier": 1}
            ).to_list(length=None)
            for c in all_carriers:
                c["_id"] = str(c["_id"])
        except Exception:
            all_carriers = []

        return {
            "signals": {},
            "best_match": None,
            "alternatives": [],
            "all_carriers": [{"_id": c["_id"], "carrier": c["carrier"]} for c in all_carriers],
            "needs_confirmation": True,
            "message": f"Error analyzing EDI: {str(e)}. Please select a carrier manually."
        }


# ═══════════════════════════════════════════════════════════════
# VALIDATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/label")
async def validate_label(
    carrier_id: str = Form(...),
    label_file: UploadFile = File(...),
    spec_name: str = Form(None),
):
    db = get_database()

    try:
        carrier = await db.carriers.find_one({"_id": ObjectId(carrier_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid carrier ID")

    if not carrier:
        raise HTTPException(status_code=404, detail="Carrier not found")

    rules = carrier.get("rules", [])

    if not rules:
        raise HTTPException(
            status_code=400,
            detail="No rule versions found for this carrier. Upload specs first."
        )

    active_rule = next(
        (r for r in rules if r.get("status") == "active"),
        None
    )

    if not active_rule:
        raise HTTPException(status_code=400, detail="No active rule version found.")

    label_rules = active_rule.get("label_rules", {})

    if not label_rules:
        raise HTTPException(
            status_code=400,
            detail="No label rules found in active version."
        )

    label_path = await save_upload_file(label_file, "label")
    file_ext = os.path.splitext(label_path)[1].lower()

    validator = LabelValidator(label_rules)

    if file_ext in [".zpl", ".txt"]:
        label_text = read_text_file(label_path)
        result = await validator.validate(label_text.encode("utf-8"), is_zpl=True)

    elif file_ext in [".png", ".jpg", ".jpeg"]:
        image_bytes = read_file_content(label_path)
        result = await validator.validate(image_bytes, is_zpl=False)

    elif file_ext == ".pdf":
        image_bytes = read_file_content(label_path)
        result = await validator.validate(image_bytes, is_zpl=False)

    else:
        raise HTTPException(status_code=400, detail="Unsupported label file type")

    await db.validation_results.insert_one({
        "carrier_id": carrier_id,
        "carrier_name": carrier.get("carrier", ""),
        "spec_name": spec_name,
        "validation_type": "label",
        "status": result["status"],
        "errors": result["errors"],
        "corrected_script": result.get("corrected_label_script"),
        "original_file_path": label_path,
        "created_at": datetime.utcnow()
    })

    return {"success": True, "validation": result}


@router.post("/edi")
async def validate_edi(
    carrier_id: str = Form(...),
    edi_file: UploadFile = File(...),
):
    db = get_database()

    try:
        carrier = await db.carriers.find_one({"_id": ObjectId(carrier_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid carrier ID")

    if not carrier:
        raise HTTPException(status_code=404, detail="Carrier not found")

    rules = carrier.get("rules", [])

    active_rule = next(
        (r for r in rules if r.get("status") == "active"),
        None
    )

    edi_rules = active_rule.get("edi_rules", {}) if active_rule else {}

    if not edi_rules:
        raise HTTPException(
            status_code=400,
            detail="No EDI rules found for this carrier. Upload specs first."
        )

    edi_path = await save_upload_file(edi_file, "edi")
    file_ext = os.path.splitext(edi_path)[1].lower()

    if file_ext not in [".edi", ".txt", ".csv", ".xml", ".json"]:
        raise HTTPException(status_code=400, detail="Unsupported EDI file format")

    try:
        edi_content = read_text_file(edi_path)
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to read EDI file as text")

    validator = EDIValidator(edi_rules)
    result = await validator.validate(edi_content)

    await db.validation_results.insert_one({
        "carrier_id": carrier_id,
        "carrier_name": carrier.get("carrier", ""),
        "validation_type": "edi",
        "status": result["status"],
        "errors": result["errors"],
        "corrected_script": result.get("corrected_edi_script"),
        "original_file_path": edi_path,
        "created_at": datetime.utcnow()
    })

    return {"success": True, "validation": result}


@router.get("/history/{carrier_id}")
async def get_validation_history(carrier_id: str, limit: int = 10):
    db = get_database()

    history = await db.validation_results.find(
        {"carrier_id": carrier_id}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)

    for item in history:
        item["_id"] = str(item["_id"])

    return {"success": True, "history": history}