"""
Mandatory Fields API
====================
Add to your main.py:
    from app.routes.mandatory_fields import router as mandatory_fields_router
    app.include_router(mandatory_fields_router)

This lets users manage mandatory field overrides through the UI.
No hardcoding — everything lives in MongoDB.

MongoDB Collection: mandatory_field_overrides
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter()


class MandatoryFieldRequest(BaseModel):
    carrier: str
    field: str
    pattern: Optional[str] = None
    description: Optional[str] = ""


class MandatoryFieldResponse(BaseModel):
    success: bool
    message: str


@router.post("/api/carriers/{carrier_name}/mandatory-fields", response_model=MandatoryFieldResponse)
async def add_mandatory_field_endpoint(carrier_name: str, req: MandatoryFieldRequest):
    """
    Add a mandatory field for a carrier.
    This field will ALWAYS be checked during validation, even if
    the LLM extraction didn't include it.
    """
    from app.database import get_db
    from app.services.label_validator import add_mandatory_field

    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    success = add_mandatory_field(
        db,
        carrier=carrier_name,
        field=req.field,
        pattern=req.pattern,
        description=req.description or f"User-added mandatory field for {carrier_name}",
        source="user_added",
    )

    if success:
        return MandatoryFieldResponse(
            success=True,
            message=f"'{req.field}' is now mandatory for {carrier_name}."
        )
    raise HTTPException(status_code=500, detail="Failed to add mandatory field")


@router.delete("/api/carriers/{carrier_name}/mandatory-fields/{field_name}", response_model=MandatoryFieldResponse)
async def remove_mandatory_field_endpoint(carrier_name: str, field_name: str):
    """Remove a mandatory field override."""
    from app.database import get_db
    from app.services.label_validator import remove_mandatory_field

    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    success = remove_mandatory_field(db, carrier_name, field_name)

    if success:
        return MandatoryFieldResponse(
            success=True,
            message=f"'{field_name}' is no longer a mandatory override for {carrier_name}."
        )
    return MandatoryFieldResponse(
        success=False,
        message=f"No override found for '{field_name}' on {carrier_name}."
    )


@router.get("/api/carriers/{carrier_name}/mandatory-fields")
async def list_mandatory_fields_endpoint(carrier_name: str):
    """List all mandatory field overrides for a carrier."""
    from app.database import get_db
    from app.services.label_validator import list_mandatory_fields

    db = get_db()
    fields = list_mandatory_fields(db, carrier_name)

    return {
        "carrier": carrier_name,
        "mandatory_fields": fields,
        "count": len(fields),
    }