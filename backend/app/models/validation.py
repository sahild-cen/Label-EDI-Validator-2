from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class ValidationError(BaseModel):
    field: str
    expected: str
    actual: str
    description: str
    location: Optional[str] = None


class LabelValidationResponse(BaseModel):
    status: str
    errors: List[ValidationError]
    corrected_label_script: Optional[str] = None
    label_preview_url: Optional[str] = None
    compliance_score: float


class EDIValidationResponse(BaseModel):
    status: str
    errors: List[ValidationError]
    corrected_edi_script: Optional[str] = None
    compliance_score: float


class ValidationResultCreate(BaseModel):
    carrier_id: str
    validation_type: str
    status: str
    errors: List[Dict[str, Any]]
    corrected_script: Optional[str] = None
    original_file_url: Optional[str] = None


class ValidationResultResponse(BaseModel):
    id: str
    carrier_id: str
    validation_type: str
    status: str
    errors: List[Dict[str, Any]]
    corrected_script: Optional[str]
    original_file_url: Optional[str]
    created_at: datetime


class ExtractedRule(BaseModel):
    field: str
    required: bool = False
    regex: str = ""
    description: str = ""


class ExtractionResult(BaseModel):
    rules: List[ExtractedRule]