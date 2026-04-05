from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class CarrierCreate(BaseModel):
    name: str


class CarrierResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class CarrierSpecCreate(BaseModel):
    carrier_id: str
    label_rules: Optional[Dict[str, Any]] = {}
    edi_rules: Optional[Dict[str, Any]] = {}
    label_spec_url: Optional[str] = None
    edi_spec_url: Optional[str] = None


class CarrierSpecResponse(BaseModel):
    id: str
    carrier_id: str
    label_rules: Dict[str, Any]
    edi_rules: Dict[str, Any]
    label_spec_url: Optional[str]
    edi_spec_url: Optional[str]
    created_at: datetime
    updated_at: datetime
