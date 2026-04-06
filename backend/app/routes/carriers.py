from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from typing import Optional
from app.services.spec_engine import SpecEngine
from app.utils.file_handler import save_upload_file
from app.database import get_database
from bson import ObjectId
import shutil
import os
import pathlib

router = APIRouter(prefix="/api/carriers", tags=["carriers"])


# ═══════════════════════════════════════════════════════════════
# UPLOAD NEW CARRIER
# (UPDATED: now stores label_spec_path / edi_spec_path in MongoDB)
# ═══════════════════════════════════════════════════════════════

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

    # Run the full rule extraction pipeline
    result = await spec_engine.process_spec_upload(
        carrier_name=carrier_name,
        label_spec_path=label_spec_path,
        edi_spec_path=edi_spec_path
    )

    # Store the spec file paths in the carrier document
    # (spec_engine stores rules but not the file paths)
    db = get_database()
    update_fields = {}
    if label_spec_path:
        update_fields["label_spec_path"] = label_spec_path
    if edi_spec_path:
        update_fields["edi_spec_path"] = edi_spec_path

    if update_fields:
        await db.carriers.update_one(
            {"carrier": carrier_name},
            {"$set": update_fields}
        )

    return {
        "success": True,
        "message": f"Carrier '{carrier_name}' specs uploaded successfully",
        "data": result
    }


# ═══════════════════════════════════════════════════════════════
# LIST CARRIERS (includes spec paths so frontend knows what exists)
# ═══════════════════════════════════════════════════════════════

@router.get("/list")
async def list_carriers():
    db = get_database()
    carriers = await db.carriers.find(
        {},
        {"_id": 1, "carrier": 1, "label_spec_path": 1, "edi_spec_path": 1}
    ).to_list(length=None)

    for carrier in carriers:
        carrier["_id"] = str(carrier["_id"])

    return {"success": True, "carriers": carriers}


# ═══════════════════════════════════════════════════════════════
# GET SINGLE CARRIER (full document)
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# DELETE CARRIER
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# RENAME CARRIER
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# UPDATE / REPLACE SPEC FILE
# Re-runs the full rule extraction pipeline (same as initial upload)
# ═══════════════════════════════════════════════════════════════

@router.put("/{carrier_id}/update-spec")
async def update_carrier_spec(
    carrier_id: str,
    spec_type: str = Form(...),
    spec_file: UploadFile = File(...),
):
    """
    Replace or add a label/EDI spec PDF for an existing carrier.
    1. Saves new file to disk
    2. Removes old file from disk
    3. Updates file path in MongoDB
    4. Re-runs the FULL rule extraction pipeline (same as first upload)
    """
    db = get_database()

    # Validate carrier exists
    try:
        carrier = await db.carriers.find_one({"_id": ObjectId(carrier_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid carrier ID")

    if not carrier:
        raise HTTPException(status_code=404, detail="Carrier not found")

    if spec_type not in ("label", "edi"):
        raise HTTPException(status_code=400, detail="spec_type must be 'label' or 'edi'")

    # Save the new file to disk
    new_path = await save_upload_file(spec_file, f"{spec_type}_spec")

    # Delete old file from disk if it exists
    path_key = f"{spec_type}_spec_path"
    old_path = carrier.get(path_key)
    if old_path and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except Exception:
            pass

    # Update MongoDB with the new file path
    await db.carriers.update_one(
        {"_id": ObjectId(carrier_id)},
        {"$set": {path_key: new_path}}
    )

    # Re-run the FULL rule extraction pipeline
    # This is the same process as the initial upload —
    # structured extraction + AI extraction + versioned save
    carrier_name = carrier["carrier"]
    spec_engine = SpecEngine()

    try:
        if spec_type == "label":
            result = await spec_engine.process_spec_upload(
                carrier_name=carrier_name,
                label_spec_path=new_path,
                edi_spec_path=None,
            )
        else:
            result = await spec_engine.process_spec_upload(
                carrier_name=carrier_name,
                label_spec_path=None,
                edi_spec_path=new_path,
            )

        return {
            "success": True,
            "message": f"{spec_type.title()} spec updated for '{carrier_name}'. Rules re-extracted.",
            "file_path": new_path,
            "data": result,
        }
    except Exception as e:
        # File is saved even if extraction fails — user can retry
        return {
            "success": True,
            "message": f"{spec_type.title()} spec file saved but rule extraction failed: {str(e)}",
            "file_path": new_path,
            "extraction_error": str(e),
        }


# ═══════════════════════════════════════════════════════════════
# SERVE SPEC FILES (PDF viewer in frontend)
# ═══════════════════════════════════════════════════════════════

@router.get("/files/{file_path:path}")
async def serve_spec_file(file_path: str):
    """
    Serve uploaded spec PDF files for viewing in the frontend iframe.
    Security: only serves files from the uploads directory.
    """
    uploads_dir = pathlib.Path("uploads").resolve()
    requested = pathlib.Path(file_path).resolve()

    # If path is relative, resolve against uploads dir
    if not requested.is_absolute() or not str(requested).startswith(str(uploads_dir)):
        requested = (uploads_dir / file_path).resolve()

    # Security check
    if not str(requested).startswith(str(uploads_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not requested.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(requested),
        media_type="application/pdf",
        filename=requested.name,
    )


# ═══════════════════════════════════════════════════════════════
# VERSIONING ENDPOINTS (unchanged from your original)
# ═══════════════════════════════════════════════════════════════

spec_engine = SpecEngine()


@router.post("/{carrier_name}/rollback/{version}")
async def rollback_carrier_rules(carrier_name: str, version: int):
    return await spec_engine.rollback_to_version(carrier_name, version)


@router.get("/{carrier_name}/versions")
async def list_carrier_versions(carrier_name: str):
    return await spec_engine.list_versions(carrier_name)


@router.get("/{carrier_name}/compare/{v1}/{v2}")
async def compare_rule_versions(carrier_name: str, v1: int, v2: int):
    return await spec_engine.compare_versions(carrier_name, v1, v2)


@router.post("/{carrier_name}/simulate/{v1}/{v2}")
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