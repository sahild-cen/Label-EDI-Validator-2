from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from typing import Optional
from app.services.spec_engine import SpecEngine
from app.utils.file_handler import save_upload_file
from app.database import get_database
from bson import ObjectId
import shutil
import os

router = APIRouter(prefix="/api/carriers", tags=["carriers"])


@router.post("/upload")
async def upload_carrier_spec(
    carrier_name: str = Form(...),
    label_spec: Optional[UploadFile] = File(None),
    edi_spec: Optional[UploadFile] = File(None)
):
    spec_engine = SpecEngine()

    label_spec_path = None
    edi_spec_path = None

    if label_spec:
        label_spec_path = await save_upload_file(label_spec, "label_spec")

    if edi_spec:
        edi_spec_path = await save_upload_file(edi_spec, "edi_spec")

    result = await spec_engine.process_spec_upload(
        carrier_name=carrier_name,
        label_spec_path=label_spec_path,
        edi_spec_path=edi_spec_path
    )

    return {
        "success": True,
        "message": f"Carrier \'{carrier_name}\' specs uploaded successfully",
        "data": result
    }


@router.get("/list")
async def list_carriers():
    db = get_database()
    carriers = await db.carriers.find({}, {"_id": 1, "carrier": 1}).to_list(length=None)

    for carrier in carriers:
        carrier["_id"] = str(carrier["_id"])

    return {"success": True, "carriers": carriers}


@router.get("/{carrier_id}")
async def get_carrier(carrier_id: str):
    db = get_database()

    try:
        carrier = await db.carriers.find_one({"_id": ObjectId(carrier_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid carrier ID")

    if not carrier:
        raise HTTPException(status_code=404, detail="Carrier not found")

    carrier["_id"] = str(carrier["_id"])
    return {"success": True, "carrier": carrier}


@router.delete("/{carrier_id}")
async def delete_carrier(carrier_id: str):
    db = get_database()

    try:
        result = await db.carriers.delete_one({"_id": ObjectId(carrier_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid carrier ID")

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Carrier not found")

    return {"success": True, "message": "Carrier deleted successfully"}


# ── Rename carrier ──

@router.patch("/{carrier_id}/rename")
async def rename_carrier(carrier_id: str, request: Request):
    db = get_database()

    try:
        body = await request.json()
        new_name = body.get("carrier_name", "").strip()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    if not new_name:
        raise HTTPException(status_code=400, detail="Carrier name cannot be empty")

    try:
        result = await db.carriers.update_one(
            {"_id": ObjectId(carrier_id)},
            {"$set": {"carrier": new_name}}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid carrier ID")

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Carrier not found")

    return {"success": True, "message": f"Carrier renamed to '{new_name}'"}


# --- Versioning endpoints ---

spec_engine = SpecEngine()


@router.post("/carriers/{carrier_name}/rollback/{version}")
async def rollback_carrier_rules(carrier_name: str, version: int):
    return await spec_engine.rollback_to_version(carrier_name, version)


@router.get("/carriers/{carrier_name}/versions")
async def list_carrier_versions(carrier_name: str):
    return await spec_engine.list_versions(carrier_name)


@router.get("/carriers/{carrier_name}/compare/{v1}/{v2}")
async def compare_rule_versions(carrier_name: str, v1: int, v2: int):
    return await spec_engine.compare_versions(carrier_name, v1, v2)


@router.post("/carriers/{carrier_name}/simulate/{v1}/{v2}")
async def simulate_validation(
    carrier_name: str,
    v1: int,
    v2: int,
    file: UploadFile = File(...)
):
    temp_path = f"temp_{file.filename}"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = await spec_engine.simulate_validation(carrier_name, v1, v2, temp_path)

    os.remove(temp_path)

    return result