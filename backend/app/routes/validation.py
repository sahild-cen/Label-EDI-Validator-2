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
    """
    db = get_database()

    try:
        content = await label_file.read()
        script = content.decode("utf-8", errors="ignore")

        # Parse label with the spatial ZPL parser
        parsed_label = parse_zpl_script(script)

        if not parsed_label:
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
                "message": "Could not parse the label file. Please select a carrier manually.",
            }

        result = await match_carrier_from_label(parsed_label, db)
        return result

    except Exception as e:
        # Still return carriers for manual fallback
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
            "message": f"Error detecting spec: {str(e)}",
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
        edi_content = content.decode("utf-8", errors="ignore")

        result = await match_carrier_from_edi(edi_content, db)
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
            "message": f"Error detecting EDI spec: {str(e)}",
        }


# ═══════════════════════════════════════════════════════════════
# LABEL VALIDATION
# ═══════════════════════════════════════════════════════════════

@router.post("/label")
async def validate_label(
    carrier_id: str = Form(...),
    label_file: UploadFile = File(...),
    is_zpl: str = Form("false"),
    spec_name: str = Form(None),
):
    db = get_database()

    try:
        carrier = await db.carriers.find_one({"_id": ObjectId(carrier_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid carrier ID")

    if not carrier:
        raise HTTPException(status_code=404, detail="Carrier not found")

    carrier_name = carrier.get("carrier", "")

    print("\n" + "=" * 70)
    print(f"LABEL VALIDATION REQUEST")
    print(f"=" * 70)
    print(f"   Carrier:    {carrier_name} (ID: {carrier_id})")
    print(f"   Spec Name:  {spec_name or 'auto'}")
    print(f"   Is ZPL:     {is_zpl}")

    rules = carrier.get("rules", [])

    if not rules:
        raise HTTPException(
            status_code=400,
            detail="No rule versions found for this carrier. Upload specs first.",
        )

    # If spec_name is provided, try to find rules for that specific spec
    active_rule = None
    if spec_name:
        active_rule = next(
            (r for r in rules if r.get("spec_name") == spec_name and r.get("status") == "active"),
            None,
        )

    # Fallback to any active rule
    if not active_rule:
        active_rule = next(
            (r for r in rules if r.get("status") == "active"),
            None,
        )

    if not active_rule:
        raise HTTPException(status_code=400, detail="No active rule version found.")

    label_rules = active_rule.get("label_rules", {})

    if not label_rules:
        raise HTTPException(
            status_code=400,
            detail="No label rules found in active version.",
        )

    print(f"   Rule Version: {active_rule.get('version', '?')}")
    print(f"   Label Rules Keys: {list(label_rules.keys())}")

    # Read label file
    label_path = await save_upload_file(label_file, "labels")
    file_ext = os.path.splitext(label_path)[1].lower()

    is_zpl_file = is_zpl.lower() == "true" or file_ext == ".zpl"

    try:
        if is_zpl_file:
            label_content = read_text_file(label_path)
            print(f"   File Type:  ZPL ({len(label_content)} chars)")
        else:
            label_content = read_file_content(label_path)
            print(f"   File Type:  Image/PDF")
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to read label file")

    # Pass carrier_name so mandatory overrides work
    validator = LabelValidator(label_rules, carrier_name=carrier_name)
    result = await validator.validate(label_content, is_zpl=is_zpl_file)

    # Save to history
    await db.validation_results.insert_one({
        "carrier_id": carrier_id,
        "carrier_name": carrier_name,
        "validation_type": "label",
        "spec_name": spec_name,
        "status": result["status"],
        "errors": result["errors"],
        "corrected_script": result.get("corrected_label_script"),
        "compliance_score": result.get("compliance_score", 0),
        "original_file_path": label_path,
        "created_at": datetime.utcnow(),
    })

    return {"success": True, "validation": result}


# ═══════════════════════════════════════════════════════════════
# EDI VALIDATION
# ═══════════════════════════════════════════════════════════════

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

    carrier_name = carrier.get("carrier", "")

    rules = carrier.get("rules", [])

    if not rules:
        raise HTTPException(
            status_code=400,
            detail="No rule versions found for this carrier. Upload specs first.",
        )

    active_rule = next(
        (r for r in rules if r.get("status") == "active"),
        None,
    )

    if not active_rule:
        raise HTTPException(status_code=400, detail="No active rule version found.")

    edi_rules = active_rule.get("edi_rules", {})

    if not edi_rules:
        raise HTTPException(
            status_code=400,
            detail="No EDI rules found in active version.",
        )

    print("\n" + "=" * 70)
    print(f"EDI VALIDATION REQUEST")
    print(f"=" * 70)
    print(f"   Carrier:      {carrier_name} (ID: {carrier_id})")
    print(f"   Rule Version: {active_rule.get('version', '?')}")
    print(f"   EDI Rules Keys: {list(edi_rules.keys())}")

    # Read EDI file
    edi_path = await save_upload_file(edi_file, "edi")
    file_ext = os.path.splitext(edi_path)[1].lower()

    if file_ext not in [".edi", ".txt", ".csv", ".xml", ".json"]:
        raise HTTPException(status_code=400, detail="Unsupported EDI file format")

    try:
        edi_content = read_text_file(edi_path)
        print(f"   File Size:    {len(edi_content)} chars")
        print(f"   File Ext:     {file_ext}")
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to read EDI file as text")

    validator = EDIValidator(edi_rules)
    result = await validator.validate(edi_content)

    # Save to history
    await db.validation_results.insert_one({
        "carrier_id": carrier_id,
        "carrier_name": carrier_name,
        "validation_type": "edi",
        "status": result["status"],
        "errors": result["errors"],
        "corrected_script": result.get("corrected_edi_script"),
        "compliance_score": result.get("compliance_score", 0),
        "original_file_path": edi_path,
        "created_at": datetime.utcnow(),
    })

    return {"success": True, "validation": result}


# ═══════════════════════════════════════════════════════════════
# VALIDATION HISTORY
# ═══════════════════════════════════════════════════════════════

@router.get("/history/{carrier_id}")
async def get_validation_history(carrier_id: str, limit: int = 10):
    db = get_database()

    history = await db.validation_results.find(
        {"carrier_id": carrier_id}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)

    for item in history:
        item["_id"] = str(item["_id"])

    return {"success": True, "history": history}