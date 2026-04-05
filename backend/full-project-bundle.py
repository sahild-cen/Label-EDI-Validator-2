# ══════════════════════════════════════════════════════════════
# CARRIER LABEL & EDI VALIDATION SYSTEM - COMPLETE PROJECT
# ══════════════════════════════════════════════════════════════
#
# PROJECT STRUCTURE:
# ─────────────────
# backend/
# ├── app/
# │   ├── __init__.py
# │   ├── main.py
# │   ├── config.py
# │   ├── database.py
# │   ├── models/
# │   │   ├── __init__.py
# │   │   └── validation.py
# │   ├── routes/
# │   │   ├── __init__.py
# │   │   ├── carriers.py
# │   │   └── validation.py
# │   ├── services/
# │   │   ├── __init__.py
# │   │   ├── spec_engine.py
# │   │   ├── claude_service.py
# │   │   ├── rule_extractor.py
# │   │   ├── rule_normalizer.py
# │   │   ├── rule_canonicalizer.py
# │   │   ├── rule_merger.py
# │   │   ├── pdf_parser.py
# │   │   ├── label_validator.py
# │   │   ├── edi_validator.py
# │   │   └── zpl_parser.py
# │   └── utils/
# │       ├── __init__.py
# │       ├── file_handler.py
# │       └── pdf_extractor.py
# ├── uploads/                (auto-created)
# ├── .env
# ├── .env.example
# └── requirements.txt
#
# frontend/
# ├── src/
# │   ├── App.tsx             (React artifact already provided)
# │   ├── main.tsx
# │   ├── index.css
# │   ├── components/
# │   │   └── Navigation.tsx
# │   ├── pages/
# │   │   ├── CarrierSetup.tsx
# │   │   └── ValidationDashboard.tsx
# │   └── services/
# │       └── api.ts
# ├── index.html
# ├── package.json
# └── vite.config.ts
#
# ══════════════════════════════════════════════════════════════
# HOW TO USE THIS FILE:
# ══════════════════════════════════════════════════════════════
#
# OPTION 1 (Recommended): Run the auto-splitter at the bottom
#   python full_project.py
#   This will create all folders and files automatically.
#
# OPTION 2: Manually copy each section between the
#   "# ═══ FILE: ..." markers into the correct path.
#
# ══════════════════════════════════════════════════════════════


import os

FILES = {}

# ══════════════════════════════════════════════════════════════
# FILE: .env.example
# ══════════════════════════════════════════════════════════════
FILES[".env.example"] = '''# Claude AI (Azure AI Foundry)
CLAUDE_ENDPOINT=https://your-foundry-endpoint.azure.com
CLAUDE_DEPLOYMENT=claude-opus-your-deployment-name
CLAUDE_API_KEY=your-api-key-here

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=label_edi_validator
'''

# ══════════════════════════════════════════════════════════════
# FILE: requirements.txt
# ══════════════════════════════════════════════════════════════
FILES["requirements.txt"] = '''fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6
pydantic==2.5.3
pydantic-settings==2.1.0
python-dotenv==1.0.0

# PDF processing
PyMuPDF==1.24.0
pdfplumber==0.10.3

# Image processing
opencv-python==4.9.0.80
pytesseract==0.3.10
pyzbar==0.1.9
Pillow==10.2.0
numpy==1.26.3

# Database
pymongo==4.6.1
motor==3.3.2

# HTTP
httpx==0.26.0

# Claude AI
anthropic>=0.39.0

# Auth (optional)
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/__init__.py
# ══════════════════════════════════════════════════════════════
FILES["app/__init__.py"] = ''

# ══════════════════════════════════════════════════════════════
# FILE: app/main.py
# ══════════════════════════════════════════════════════════════
FILES["app/main.py"] = '''from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import carriers, validation

app = FastAPI(
    title="Label & EDI Validation API",
    description="Specification-driven validation tool for shipping labels and EDI files",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(carriers.router)
app.include_router(validation.router)


@app.get("/")
async def root():
    return {
        "message": "Label & EDI Validation API",
        "status": "running",
        "version": "2.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/database.py
# ══════════════════════════════════════════════════════════════
FILES["app/database.py"] = '''import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "label_edi_validator")

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]


def get_database():
    return db
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/config.py
# ══════════════════════════════════════════════════════════════
FILES["app/config.py"] = '''from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "label_edi_validator"
    claude_endpoint: str = ""
    claude_deployment: str = ""
    claude_api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings():
    return Settings()
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/models/__init__.py
# ══════════════════════════════════════════════════════════════
FILES["app/models/__init__.py"] = ''

# ══════════════════════════════════════════════════════════════
# FILE: app/models/validation.py
# ══════════════════════════════════════════════════════════════
FILES["app/models/validation.py"] = '''from pydantic import BaseModel
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
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/routes/__init__.py
# ══════════════════════════════════════════════════════════════
FILES["app/routes/__init__.py"] = ''

# ══════════════════════════════════════════════════════════════
# FILE: app/routes/carriers.py
# ══════════════════════════════════════════════════════════════
FILES["app/routes/carriers.py"] = '''from fastapi import APIRouter, UploadFile, File, Form, HTTPException
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
        "message": f"Carrier \\'{carrier_name}\\' specs uploaded successfully",
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
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/routes/validation.py
# ══════════════════════════════════════════════════════════════
FILES["app/routes/validation.py"] = '''import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.label_validator import LabelValidator
from app.services.edi_validator import EDIValidator
from app.utils.file_handler import save_upload_file, read_file_content, read_text_file
from app.database import get_database
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/api/validate", tags=["validation"])


@router.post("/label")
async def validate_label(
    carrier_id: str = Form(...),
    label_file: UploadFile = File(...)
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
    edi_file: UploadFile = File(...)
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
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/__init__.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/__init__.py"] = ''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/claude_service.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/claude_service.py"] = '''import os
import re
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

endpoint = os.getenv("CLAUDE_ENDPOINT")
deployment_name = os.getenv("CLAUDE_DEPLOYMENT")
api_key = os.getenv("CLAUDE_API_KEY")

client = None

try:
    from anthropic import AnthropicFoundry
    client = AnthropicFoundry(api_key=api_key, base_url=endpoint)
    print("Claude client initialized (AnthropicFoundry)")
except ImportError:
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        print("Claude client initialized (Anthropic)")
    except ImportError:
        print("No Anthropic client available. Install anthropic package.")


def extract_json_from_text(text):
    text = re.sub(r"```json\\s*", "", text)
    text = re.sub(r"```\\s*", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\\{[\\s\\S]*\\}", text)
    if not match:
        return None

    json_text = match.group(0)

    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\\s*([}\\]])", r"\\1", json_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            print("JSON decode error after cleanup")
            return None


def extract_rules_from_chunk(chunk, section_title=""):
    if not client:
        print("Claude client not initialized")
        return []

    context = f\\' (from section: "{section_title}")\\' if section_title else ""

    prompt = f"""You are an expert in logistics carrier label and EDI specifications.

Extract ONLY validation rules from the following document text{context}.

Focus on rules related to:
- Mandatory/required fields
- Field formats and allowed values
- Regex patterns (ONLY if clearly defined in text)
- Barcode structure, type, and encoding
- Routing information and routing barcodes
- Postal code / address format requirements
- Tracking / shipment number formats
- Label dimensions and layout constraints
- EDI segment requirements and element formats
- Weight, service type, country code rules

IGNORE completely:
- Document history and version info
- Copyright notices and legal text
- Headers, footers, page numbers
- Table of contents
- Descriptions that do not define a rule

Return STRICT JSON format only. No explanation before or after.

{{"rules": [{{"field_name": "<descriptive_name>", "required": true, "format": "<format if applicable>", "regex": "<regex ONLY if clearly defined, otherwise empty string>", "description": "<concise rule description>"}}]}}

IMPORTANT:
- Do NOT invent regex patterns. Only include regex if the document clearly specifies a format.
- If no rules are found, return: {{"rules": []}}

TEXT:
{chunk}
"""

    try:
        response = client.messages.create(
            model=deployment_name,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        if not response.content:
            return []

        text = response.content[0].text
        data = extract_json_from_text(text)

        if not data:
            print("Failed to parse JSON from Claude response")
            return []

        return data.get("rules", [])

    except Exception as e:
        print(f"Claude extraction error: {str(e)}")
        return []
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/pdf_parser.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/pdf_parser.py"] = '''import fitz  # PyMuPDF
import re
from typing import List, Dict


def extract_text_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            boundary = text.rfind(".", start + chunk_size - 300, end)
            if boundary > start:
                end = boundary + 1

        chunks.append(text[start:end].strip())
        start += chunk_size - overlap

    return [c for c in chunks if len(c) > 20]


def detect_sections(text: str) -> List[Dict]:
    lines = text.split("\\n")
    sections = []
    current_section = {"title": "intro", "content": []}

    heading_pattern = re.compile(r"^(\\d+(\\.\\d+)*)\\s+[A-Z][A-Za-z\\s\\-\\/\\(\\)&]+$")
    caps_heading = re.compile(r"^[A-Z][A-Z\\s\\-\\/\\(\\)&]{5,}$")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        is_heading = heading_pattern.match(line) or (
            caps_heading.match(line) and len(line) < 60
        )

        if is_heading:
            if current_section["content"] or current_section["title"] != "intro":
                sections.append(current_section)
            current_section = {"title": line, "content": []}
        else:
            current_section["content"].append(line)

    if current_section["content"]:
        sections.append(current_section)

    return sections


RULE_SECTION_KEYWORDS = [
    "label", "barcode", "routing", "field", "data", "format",
    "code", "shipment", "address", "tracking", "license plate",
    "dimension", "weight", "postal", "service", "encoding",
    "mandatory", "required", "element", "segment", "edi",
    "specification", "validation", "structure"
]


def filter_rule_sections(sections: List[Dict]) -> List[Dict]:
    filtered = []

    for section in sections:
        title = section["title"].lower()

        if any(keyword in title for keyword in RULE_SECTION_KEYWORDS):
            filtered.append(section)
            continue

        preview = " ".join(section["content"][:5]).lower()
        if any(keyword in preview for keyword in RULE_SECTION_KEYWORDS[:10]):
            filtered.append(section)

    return filtered if filtered else sections
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/rule_extractor.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/rule_extractor.py"] = '''"""
11-Step Rule Extraction Pipeline
"""

from app.services.pdf_parser import (
    extract_text_from_pdf, chunk_text,
    detect_sections, filter_rule_sections
)
from app.services.claude_service import extract_rules_from_chunk
from app.services.rule_normalizer import normalize_rules
from app.services.rule_canonicalizer import canonicalize_rules
from app.services.rule_merger import merge_rules_by_field


RULE_KEYWORDS = [
    "barcode", "label", "postal code", "postcode", "tracking",
    "license plate", "routing", "field", "format", "mandatory",
    "required", "length", "must", "shall", "digit", "numeric",
    "alphanumeric", "encoding", "dimension", "weight", "segment",
    "element", "edi", "shipment", "consignment"
]

IGNORE_FIELD_KEYWORDS = [
    "iso", "standard", "specification", "example", "guide",
    "implementation", "structure", "syntax", "transfer",
    "document", "version", "copyright", "appendix", "annex"
]


def filter_rule_chunks(chunks):
    filtered = [c for c in chunks if any(k in c.lower() for k in RULE_KEYWORDS)]
    return filtered if filtered else chunks


def filter_rules(rules):
    return [
        r for r in rules
        if not any(k in r.get("field_name", "").lower() for k in IGNORE_FIELD_KEYWORDS)
    ]


def deduplicate_rules(rules):
    seen = set()
    unique = []
    for rule in rules:
        name = rule.get("field_name", "").lower().strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(rule)
    return unique


def extract_rules_from_pdf(file_path: str) -> list:
    # Step 2
    text = extract_text_from_pdf(file_path)
    print(f"[Pipeline] Step 2: Extracted {len(text)} characters")

    if len(text.strip()) < 50:
        print("[Pipeline] Very little text extracted from PDF")
        return []

    # Step 3
    sections = detect_sections(text)
    print(f"[Pipeline] Step 3: Detected {len(sections)} sections")

    # Step 4
    rule_sections = filter_rule_sections(sections)
    print(f"[Pipeline] Step 4: {len(rule_sections)} relevant sections")

    all_rules = []

    for i, section in enumerate(rule_sections):
        section_text = "\\n".join(section["content"])
        section_title = section.get("title", f"Section {i+1}")

        if len(section_text.strip()) < 20:
            continue

        # Step 5
        chunks = chunk_text(section_text)
        relevant_chunks = filter_rule_chunks(chunks)
        print(f"[Pipeline] Step 5: Section \\'{section_title}\\' -> {len(relevant_chunks)} chunks")

        for j, chunk in enumerate(relevant_chunks):
            # Steps 6-7
            print(f"[Pipeline] Step 6-7: Chunk {j+1}/{len(relevant_chunks)} [{section_title}]")
            rules = extract_rules_from_chunk(chunk, section_title=section_title)

            if rules:
                all_rules.extend(rules)
                print(f"  -> Extracted {len(rules)} rules")
            else:
                print(f"  -> No rules found")

    print(f"[Pipeline] Raw rules total: {len(all_rules)}")

    # Filter
    filtered_rules = filter_rules(all_rules)
    print(f"[Pipeline] After filtering: {len(filtered_rules)}")

    # Deduplicate
    deduped_rules = deduplicate_rules(filtered_rules)
    print(f"[Pipeline] After dedup: {len(deduped_rules)}")

    # Step 8
    normalized_rules = normalize_rules(deduped_rules)
    print(f"[Pipeline] Step 8: Normalized {len(normalized_rules)} rules")

    # Step 9
    canonical_rules = canonicalize_rules(normalized_rules)
    print(f"[Pipeline] Step 9: Canonicalized")

    # Step 10
    merged_rules = merge_rules_by_field(canonical_rules)
    print(f"[Pipeline] Step 10: Merged -> {len(merged_rules)} final rules")

    # Step 11
    print(f"[Pipeline] Complete -- {len(merged_rules)} rules extracted")

    return merged_rules
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/rule_normalizer.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/rule_normalizer.py"] = '''FIELD_MAPPING = {
    "country code": "country_code",
    "destination country code": "country_code",
    "origin country code": "country_code",
    "postcode": "postal_code",
    "postal code": "postal_code",
    "zip code": "postal_code",
    "zip": "postal_code",
    "post code": "postal_code",
    "routing barcode": "routing_barcode",
    "routing code": "routing_barcode",
    "routing information bar code": "routing_barcode",
    "sort code": "routing_barcode",
    "license plate": "license_plate",
    "licence plate": "license_plate",
    "licence plate identifier": "license_plate",
    "sscc": "license_plate",
    "tracking number": "tracking_number",
    "tracking_number": "tracking_number",
    "consignment number": "tracking_number",
    "shipment number": "shipment_number",
    "shipment_number": "shipment_number",
    "airwaybill": "shipment_number",
    "awb": "shipment_number",
    "waybill": "shipment_number",
    "air waybill": "shipment_number",
    "consignment id": "shipment_number",
    "label width": "label_width",
    "label height": "label_height",
    "label length": "label_height",
    "label orientation": "label_orientation",
    "label size": "label_dimensions",
    "label dimensions": "label_dimensions",
    "sender name": "sender_name",
    "shipper name": "sender_name",
    "sender address": "sender_address",
    "shipper address": "sender_address",
    "receiver name": "receiver_name",
    "recipient name": "receiver_name",
    "consignee name": "receiver_name",
    "receiver address": "receiver_address",
    "recipient address": "receiver_address",
    "destination address": "receiver_address",
    "weight": "weight",
    "gross weight": "weight",
    "actual weight": "weight",
    "package weight": "weight",
    "service type": "service_type",
    "service code": "service_type",
    "product code": "service_type",
    "barcode": "barcode",
    "linear barcode": "barcode",
    "awb barcode": "barcode",
    "reference number": "reference_number",
    "reference": "reference_number",
    "customer reference": "reference_number",
    "piece count": "piece_count",
    "number of pieces": "piece_count",
    "total pieces": "piece_count",
}


def normalize_rules(rules):
    normalized = []

    for rule in rules:
        field_name = rule.get("field_name", "").lower().strip()

        standardized_field = FIELD_MAPPING.get(
            field_name,
            field_name.replace(" ", "_").replace("-", "_")
        )

        standardized_field = standardized_field.replace("__", "_").strip("_")

        normalized.append({
            "field": standardized_field,
            "required": rule.get("required", False),
            "regex": rule.get("regex", ""),
            "description": rule.get("description", "")
        })

    return normalized
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/rule_canonicalizer.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/rule_canonicalizer.py"] = '''CANONICAL_FIELDS = {
    "shipment_number": [
        "shipment_number", "shipment_identifier", "waybill_number",
        "tracking_number", "consignment_number", "airwaybill_number",
        "awb_number", "air_waybill"
    ],
    "postal_code": [
        "postal_code", "postcode", "postcode_town",
        "zip_code", "zipcode", "post_code"
    ],
    "routing_barcode": [
        "routing_barcode", "routing_information_bar_code",
        "routing_label_barcode", "routing_code", "sort_code"
    ],
    "license_plate": [
        "license_plate", "licence_plate", "licence_plate_identifier",
        "license_plate_barcode", "sscc", "sscc_barcode"
    ],
    "barcode": [
        "barcode", "linear_barcode", "awb_barcode",
        "label_barcode", "main_barcode"
    ],
    "label_dimensions": [
        "label_dimensions", "label_width", "label_length",
        "label_height", "label_size"
    ],
    "weight": [
        "weight", "gross_weight", "actual_weight",
        "package_weight", "shipment_weight"
    ],
    "sender_name": [
        "sender_name", "shipper_name", "from_name", "origin_name"
    ],
    "sender_address": [
        "sender_address", "shipper_address", "from_address", "origin_address"
    ],
    "receiver_name": [
        "receiver_name", "recipient_name", "to_name",
        "destination_name", "consignee_name"
    ],
    "receiver_address": [
        "receiver_address", "recipient_address", "to_address",
        "destination_address", "consignee_address"
    ],
    "country_code": [
        "country_code", "country", "destination_country",
        "origin_country", "iso_country_code"
    ],
    "service_type": [
        "service_type", "service_code", "product_code",
        "service_indicator", "delivery_service"
    ],
    "reference_number": [
        "reference_number", "reference", "customer_reference",
        "ref_number", "order_reference"
    ],
    "piece_count": [
        "piece_count", "pieces", "number_of_pieces",
        "total_pieces", "package_count"
    ],
}


def canonicalize_rules(rules):
    canonical_rules = []

    for rule in rules:
        field = rule.get("field", "").lower().strip()
        canonical_field = field

        for standard, variants in CANONICAL_FIELDS.items():
            if field in variants:
                canonical_field = standard
                break

        rule["field"] = canonical_field
        canonical_rules.append(rule)

    return canonical_rules
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/rule_merger.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/rule_merger.py"] = '''def merge_rules_by_field(rules):
    merged = {}

    for rule in rules:
        field = rule.get("field", "").strip()

        if not field:
            continue

        if field not in merged:
            merged[field] = {
                "field": field,
                "required": rule.get("required", False),
                "regex": rule.get("regex", ""),
                "description": rule.get("description", "")
            }
        else:
            existing = merged[field]

            if not existing.get("regex") and rule.get("regex"):
                existing["regex"] = rule["regex"]

            if rule.get("required"):
                existing["required"] = True

            desc1 = existing.get("description", "").strip()
            desc2 = rule.get("description", "").strip()

            if desc2 and desc2 not in desc1:
                if desc1:
                    existing["description"] = f"{desc1}; {desc2}"
                else:
                    existing["description"] = desc2

    return list(merged.values())
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/spec_engine.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/spec_engine.py"] = '''from typing import Dict, Any
from datetime import datetime
from app.database import get_database
from app.utils.pdf_extractor import (
    extract_structured_pdf_data,
    generate_rule_template_from_spec
)


class SpecEngine:
    def __init__(self):
        self.db = get_database()

    async def process_spec_upload(
        self,
        carrier_name: str,
        label_spec_path: str = None,
        edi_spec_path: str = None
    ) -> Dict[str, Any]:

        label_rules = {}
        edi_rules = {}
        ai_extracted_rules = []

        # --- LABEL SPEC ---
        if label_spec_path:
            spec_data = extract_structured_pdf_data(label_spec_path)
            label_rules, structured_conf = generate_rule_template_from_spec(
                spec_data, spec_type="label"
            )
            final_confidence = structured_conf

            try:
                from app.services.rule_extractor import extract_rules_from_pdf
                ai_rules = extract_rules_from_pdf(label_spec_path)
                if ai_rules:
                    ai_extracted_rules = ai_rules
                    for rule in ai_rules:
                        field = rule.get("field", "")
                        if field and field not in label_rules.get("field_formats", {}):
                            if "field_formats" not in label_rules:
                                label_rules["field_formats"] = {}
                            label_rules["field_formats"][field] = {
                                "pattern": rule.get("regex", ""),
                                "required": rule.get("required", False),
                                "description": rule.get("description", "")
                            }
                        if rule.get("required") and field:
                            if field not in label_rules.get("required_fields", []):
                                label_rules.setdefault("required_fields", []).append(field)

                    if len(ai_rules) > 3:
                        final_confidence = min(
                            0.5 * structured_conf + 0.5 * min(len(ai_rules) / 10, 1.0),
                            1.0
                        )
                    print(f"AI extracted {len(ai_rules)} additional rules")
            except Exception as e:
                print(f"AI extraction failed (continuing with structured): {e}")

            if final_confidence < 0.6:
                try:
                    from app.services.ml_fallback.layout_engine import run_layout_fallback
                    ml_rules, ml_conf, _ = run_layout_fallback(spec_data.get("image_bytes"))
                    if isinstance(ml_rules, dict):
                        label_rules.update(ml_rules)
                    final_confidence = 0.6 * final_confidence + 0.4 * ml_conf
                except Exception as e:
                    print(f"ML fallback failed: {e}")

            label_rules["confidence_score"] = round(final_confidence, 2)

        # --- EDI SPEC ---
        if edi_spec_path:
            spec_data = extract_structured_pdf_data(edi_spec_path)
            edi_rules, edi_conf = generate_rule_template_from_spec(
                spec_data, spec_type="edi"
            )

            try:
                from app.services.rule_extractor import extract_rules_from_pdf
                edi_ai_rules = extract_rules_from_pdf(edi_spec_path)
                if edi_ai_rules:
                    for rule in edi_ai_rules:
                        field = rule.get("field", "")
                        if field:
                            edi_rules.setdefault("field_formats", {})[field] = {
                                "pattern": rule.get("regex", ""),
                                "required": rule.get("required", False),
                                "description": rule.get("description", "")
                            }
                    edi_conf = min(
                        0.5 * edi_conf + 0.5 * min(len(edi_ai_rules) / 8, 1.0), 1.0
                    )
            except Exception as e:
                print(f"EDI AI extraction failed: {e}")

            edi_rules["confidence_score"] = round(edi_conf, 2)

        # --- VERSION HANDLING ---
        existing = await self.db.carriers.find_one({"carrier": carrier_name})

        if existing and "rules" in existing:
            new_version = len(existing["rules"]) + 1
        else:
            new_version = 1

        rule_entry = {
            "version": new_version,
            "created_at": datetime.utcnow(),
            "label_rules": label_rules,
            "edi_rules": edi_rules,
            "ai_extracted_rules": ai_extracted_rules,
            "status": "active"
        }

        if existing and "rules" in existing:
            await self.db.carriers.update_one(
                {"carrier": carrier_name},
                {"$set": {"rules.$[].status": "inactive"}}
            )
            await self.db.carriers.update_one(
                {"carrier": carrier_name},
                {"$push": {"rules": rule_entry}}
            )
        else:
            await self.db.carriers.update_one(
                {"carrier": carrier_name},
                {
                    "$set": {"carrier": carrier_name},
                    "$push": {"rules": rule_entry}
                },
                upsert=True
            )

        return {
            "carrier_name": carrier_name,
            "version": new_version,
            "label_rules": label_rules,
            "edi_rules": edi_rules,
            "ai_rules_count": len(ai_extracted_rules)
        }

    async def get_carrier_rules(self, carrier_name: str) -> Dict[str, Any]:
        carrier = await self.db.carriers.find_one({"carrier": carrier_name})

        if not carrier or "rules" not in carrier:
            return {"label_rules": {}, "edi_rules": {}}

        active_rule = next(
            (r for r in carrier["rules"] if r["status"] == "active"), None
        )

        if not active_rule:
            return {"label_rules": {}, "edi_rules": {}}

        return {
            "version": active_rule.get("version"),
            "label_rules": active_rule.get("label_rules", {}),
            "edi_rules": active_rule.get("edi_rules", {})
        }

    async def rollback_to_version(self, carrier_name: str, version: int) -> Dict[str, Any]:
        carrier = await self.db.carriers.find_one({"carrier": carrier_name})

        if not carrier or "rules" not in carrier:
            return {"success": False, "message": "Carrier or rules not found."}

        target = next(
            (r for r in carrier["rules"] if r["version"] == version), None
        )

        if not target:
            return {"success": False, "message": "Version not found."}

        await self.db.carriers.update_one(
            {"carrier": carrier_name},
            {"$set": {"rules.$[].status": "inactive"}}
        )
        await self.db.carriers.update_one(
            {"carrier": carrier_name, "rules.version": version},
            {"$set": {"rules.$.status": "active"}}
        )

        return {
            "success": True,
            "message": f"Rolled back to version {version}",
            "active_version": version
        }

    async def list_versions(self, carrier_name: str) -> Dict[str, Any]:
        carrier = await self.db.carriers.find_one({"carrier": carrier_name})

        if not carrier or "rules" not in carrier:
            return {"carrier": carrier_name, "versions": []}

        versions = []
        for rule in carrier["rules"]:
            versions.append({
                "version": rule.get("version"),
                "created_at": rule.get("created_at"),
                "status": rule.get("status"),
                "confidence_score": rule.get("label_rules", {}).get("confidence_score"),
                "ai_rules_count": len(rule.get("ai_extracted_rules", []))
            })

        return {"carrier": carrier_name, "versions": versions}

    async def compare_versions(self, carrier_name: str, v1: int, v2: int) -> Dict[str, Any]:
        carrier = await self.db.carriers.find_one({"carrier": carrier_name})

        if not carrier or "rules" not in carrier:
            return {"error": "Carrier or rules not found."}

        rules = carrier["rules"]
        r1 = next((r for r in rules if r["version"] == v1), None)
        r2 = next((r for r in rules if r["version"] == v2), None)

        if not r1 or not r2:
            return {"error": "One or both versions not found."}

        fields_v1 = set(r1.get("label_rules", {}).get("field_formats", {}).keys())
        fields_v2 = set(r2.get("label_rules", {}).get("field_formats", {}).keys())

        return {
            "carrier": carrier_name,
            "v1": v1, "v2": v2,
            "added_fields": list(fields_v2 - fields_v1),
            "removed_fields": list(fields_v1 - fields_v2),
            "common_fields": list(fields_v1 & fields_v2),
            "v1_confidence": r1.get("label_rules", {}).get("confidence_score"),
            "v2_confidence": r2.get("label_rules", {}).get("confidence_score"),
        }

    async def simulate_validation(
        self, carrier_name: str, version_1: int, version_2: int, label_path: str
    ) -> Dict[str, Any]:

        carrier = await self.db.carriers.find_one({"carrier": carrier_name})

        if not carrier or "rules" not in carrier:
            return {"error": "Carrier or rules not found."}

        rules = carrier["rules"]
        v1 = next((r for r in rules if r["version"] == version_1), None)
        v2 = next((r for r in rules if r["version"] == version_2), None)

        if not v1 or not v2:
            return {"error": "One or both versions not found."}

        from app.services.label_validator import LabelValidator

        validator_v1 = LabelValidator(v1.get("label_rules", {}))
        result_v1 = await validator_v1.validate(label_path)

        validator_v2 = LabelValidator(v2.get("label_rules", {}))
        result_v2 = await validator_v2.validate(label_path)

        return {
            "carrier": carrier_name,
            "version_1": version_1, "version_2": version_2,
            "results": {"v1": result_v1, "v2": result_v2},
        }
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/label_validator.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/label_validator.py"] = '''import re
import cv2
import numpy as np
import pytesseract
from typing import Dict, Any, List
from app.models.validation import ValidationError

try:
    from pyzbar import pyzbar
except Exception:
    pyzbar = None


class LabelValidator:
    def __init__(self, rules: Dict[str, Any]):
        self.rules = rules

    async def validate(self, label_data: bytes, is_zpl: bool = False) -> Dict[str, Any]:
        errors: List[ValidationError] = []
        parsed_data = {}
        original_script = ""
        barcodes = []
        layout_blocks = []

        if is_zpl:
            original_script = label_data.decode("utf-8")
            from app.services.zpl_parser import parse_zpl_script
            parsed_data = parse_zpl_script(original_script)
        else:
            img = self._load_image(label_data)
            if img is None:
                return self._fail_response("Unreadable image file.")

            text_content = self._extract_text(img)
            parsed_data = self._parse_ocr_text(text_content)
            barcodes = self.detect_barcodes(img)
            layout_blocks = self.detect_layout_blocks(img)

        field_errors, field_score, field_total = self._validate_fields(parsed_data)
        barcode_errors, barcode_score, barcode_total = self._validate_barcode(barcodes, parsed_data)
        layout_errors, layout_score, layout_total = self._validate_layout(layout_blocks)

        errors.extend(field_errors)
        errors.extend(barcode_errors)
        errors.extend(layout_errors)

        total_possible = field_total + barcode_total + layout_total
        total_earned = field_score + barcode_score + layout_score
        compliance_score = round(total_earned / total_possible, 2) if total_possible > 0 else 0.0

        status = "PASS" if not errors else "FAIL"

        corrected_script = None
        if is_zpl and errors:
            corrected_script = self._auto_correct_zpl(original_script, parsed_data, errors)

        return {
            "status": status,
            "errors": [e.dict() for e in errors],
            "corrected_label_script": corrected_script,
            "compliance_score": compliance_score
        }

    def _load_image(self, image_data: bytes):
        nparr = np.frombuffer(image_data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def _extract_text(self, img) -> str:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        return pytesseract.image_to_string(gray)

    def _parse_ocr_text(self, text: str) -> Dict[str, str]:
        parsed = {}
        tracking_match = re.search(r"\\b\\d{10,22}\\b", text)
        if tracking_match:
            parsed["tracking_number"] = tracking_match.group()
        postal_match = re.search(r"\\b\\d{5}(-\\d{4})?\\b", text)
        if postal_match:
            parsed["postal_code"] = postal_match.group()
        weight_match = re.search(r"\\b\\d+(\\.\\d+)?\\s?(KG|LB|kg|lb)\\b", text, re.IGNORECASE)
        if weight_match:
            parsed["weight"] = weight_match.group()
        country_match = re.search(r"\\b[A-Z]{2}\\b", text)
        if country_match:
            parsed["country_code"] = country_match.group()
        return parsed

    def detect_barcodes(self, img) -> list:
        if pyzbar is None:
            return []
        try:
            decoded = pyzbar.decode(img)
            return [{"data": d.data.decode("utf-8"), "type": d.type} for d in decoded]
        except Exception:
            return []

    def detect_layout_blocks(self, img) -> list:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            blocks = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                if w > 30 and h > 15:
                    blocks.append({"x": x, "y": y, "w": w, "h": h})
            return blocks
        except Exception:
            return []

    def _validate_fields(self, parsed_data: dict):
        errors = []
        earned = 0.0
        total = 0.0

        field_formats = {
            k: v for k, v in self.rules.get("field_formats", {}).items()
            if k != "barcode"
        }

        for field_name, rule in field_formats.items():
            weight = 0.1
            total += weight
            required = rule.get("required", False)
            pattern = rule.get("pattern")
            value = parsed_data.get(field_name)
            passed = False

            if value and pattern:
                try:
                    if re.match(pattern, str(value)):
                        passed = True
                except re.error:
                    passed = bool(value)
            elif value and not pattern:
                passed = True

            if passed:
                earned += weight
            elif required:
                errors.append(ValidationError(
                    field=field_name,
                    expected=f"Pattern: {pattern}" if pattern else "Required field",
                    actual=value if value else "Not found",
                    description=f"{field_name} validation failed."
                ))

        return errors, earned, total

    def _validate_barcode(self, barcodes, parsed_data):
        errors = []
        earned = 0.0
        total = 0.1

        barcode_rule = self.rules.get("field_formats", {}).get("barcode", {})
        required = barcode_rule.get("required", False)
        pattern = barcode_rule.get("pattern")

        zpl_barcode = parsed_data.get("barcode")
        value = zpl_barcode if zpl_barcode else (barcodes[0]["data"] if barcodes else None)

        passed = False
        if value:
            if pattern:
                try:
                    passed = bool(re.match(pattern, value))
                except re.error:
                    passed = True
            else:
                passed = True

        if required and not passed:
            errors.append(ValidationError(
                field="barcode",
                expected=f"Pattern: {pattern}" if pattern else "At least one barcode",
                actual=value if value else "Not found",
                description="Barcode validation failed."
            ))
        else:
            earned += 0.1

        return errors, earned, total

    def _validate_layout(self, layout_blocks):
        errors = []
        earned = 0.0
        total = 0.05

        layout_rules = self.rules.get("layout_constraints", {})
        min_blocks = layout_rules.get("min_blocks", 0)

        if min_blocks and len(layout_blocks) < min_blocks:
            errors.append(ValidationError(
                field="layout",
                expected=f"At least {min_blocks} layout blocks",
                actual=f"{len(layout_blocks)} detected",
                description="Label layout incomplete."
            ))
        else:
            earned += 0.05

        return errors, earned, total

    def _auto_correct_zpl(self, original_script, parsed_data, errors):
        corrected = original_script.strip()
        additions = []

        for error in errors:
            field = error.field
            if field == "postal_code":
                additions.append("^FO50,750^FD 12345 ^FS")
            elif field == "tracking_number":
                additions.append("^FO50,780^FD 123456789012 ^FS")
            elif field == "weight":
                additions.append("^FO50,810^FD 1 KG ^FS")
            elif field == "barcode":
                additions.append("^BY3,3,120\\n^FD123456789012^FS")

        if additions:
            corrected = corrected.replace("^XZ", "")
            corrected += "\\n" + "\\n".join(additions) + "\\n^XZ"

        return corrected

    def _fail_response(self, message):
        return {
            "status": "FAIL",
            "errors": [{
                "field": "file", "expected": "Valid image",
                "actual": "Unreadable file", "description": message
            }],
            "corrected_label_script": None,
            "compliance_score": 0.0
        }
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/edi_validator.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/edi_validator.py"] = '''import re
import json
import xml.etree.ElementTree as ET
from typing import Dict, Any, List
from app.models.validation import ValidationError


class EDIValidator:
    def __init__(self, rules: Dict[str, Any]):
        self.rules = rules

    def detect_format(self, content: str) -> str:
        content_stripped = content.strip()

        if content_stripped.startswith("{") or content_stripped.startswith("["):
            try:
                json.loads(content)
                return "json"
            except Exception:
                pass

        if content_stripped.startswith("<"):
            try:
                ET.fromstring(content)
                return "xml"
            except Exception:
                pass

        if "~" in content and "*" in content:
            return "x12"

        if "\\'" in content and "+" in content:
            return "edifact"

        if "\\n" in content and len(content.split("\\n")) > 1:
            return "delimited"

        return "fixed_width"

    def parse_content(self, content: str, format_type: str) -> Dict[str, Any]:
        if format_type == "json":
            return json.loads(content)
        elif format_type == "xml":
            root = ET.fromstring(content)
            return self._xml_to_dict(root)
        elif format_type in ["x12", "edifact"]:
            return self._parse_edi_segments(content, format_type)
        elif format_type == "delimited":
            lines = content.strip().split("\\n")
            return {"lines": lines, "segments": [line.split("|") for line in lines]}
        else:
            return {"raw_content": content}

    def _xml_to_dict(self, element):
        result = {}
        for child in element:
            child_data = child.text if child.text and not list(child) else self._xml_to_dict(child)
            result[child.tag] = child_data
        return result

    def _parse_edi_segments(self, content, format_type):
        if format_type == "x12":
            seg_delim, elem_delim = "~", "*"
        else:
            seg_delim, elem_delim = "\\'", "+"

        segments = content.split(seg_delim)
        parsed = []
        for segment in segments:
            segment = segment.strip()
            if segment:
                elements = segment.split(elem_delim)
                parsed.append({
                    "segment_id": elements[0] if elements else "",
                    "elements": elements
                })
        return {"format": format_type, "segments": parsed}

    async def validate(self, edi_content: str) -> Dict[str, Any]:
        errors = []
        format_type = self.detect_format(edi_content)

        try:
            parsed_data = self.parse_content(edi_content, format_type)
        except Exception as e:
            errors.append(ValidationError(
                field="parsing",
                expected=f"Valid {format_type} format",
                actual="Parse error",
                description=f"Failed to parse EDI content: {str(e)}"
            ))
            return {
                "status": "FAIL",
                "errors": [err.dict() for err in errors],
                "corrected_edi_script": None,
                "compliance_score": 0.0
            }

        required_segments = self.rules.get("required_segments", [])
        segment_order = self.rules.get("segment_order", [])

        if format_type in ["x12", "edifact"]:
            segments = parsed_data.get("segments", [])
            segment_ids = [seg["segment_id"] for seg in segments]

            for required_seg in required_segments:
                if required_seg not in segment_ids:
                    errors.append(ValidationError(
                        field="segments",
                        expected=f"Segment \\'{required_seg}\\' present",
                        actual="Segment missing",
                        description=f"Required segment \\'{required_seg}\\' is missing"
                    ))

            if segment_order:
                actual_indices = []
                for seg in segment_order:
                    if seg in segment_ids:
                        actual_indices.append(segment_ids.index(seg))
                if actual_indices != sorted(actual_indices):
                    errors.append(ValidationError(
                        field="segment_order",
                        expected=f"Segments in order: {\\', \\'.join(segment_order)}",
                        actual=f"Actual order: {\\', \\'.join(segment_ids[:5])}...",
                        description="Segments are not in the correct order"
                    ))

            element_rules = self.rules.get("field_formats", {})
            for field_name, rule in element_rules.items():
                pattern = rule.get("pattern", "")
                required = rule.get("required", False)
                found = False
                for seg in segments:
                    for elem in seg.get("elements", []):
                        if pattern:
                            try:
                                if re.match(pattern, elem):
                                    found = True
                                    break
                            except re.error:
                                found = True
                                break
                    if found:
                        break
                if required and not found and pattern:
                    errors.append(ValidationError(
                        field=field_name,
                        expected=f"Element matching: {pattern}",
                        actual="Not found in segments",
                        description=f"Required EDI element \\'{field_name}\\' not found"
                    ))

        elif format_type == "json":
            required_fields = self.rules.get("required_fields", [])
            for field in required_fields:
                if field not in parsed_data:
                    errors.append(ValidationError(
                        field=field,
                        expected=f"Field \\'{field}\\' present",
                        actual="Field missing",
                        description=f"Required field \\'{field}\\' is missing"
                    ))

        denominator = max(
            len(required_segments or []) + len(self.rules.get("field_formats", {})) + 2, 1
        )
        compliance_score = max(0.0, 1.0 - (len(errors) / denominator))
        status = "PASS" if not errors else "FAIL"

        corrected_script = None
        if errors:
            corrected_script = self.generate_corrected_edi(
                edi_content, format_type, errors, parsed_data
            )

        return {
            "status": status,
            "errors": [e.dict() for e in errors],
            "corrected_edi_script": corrected_script,
            "compliance_score": compliance_score
        }

    def generate_corrected_edi(self, original, fmt, errors, parsed):
        if fmt in ["x12", "edifact"]:
            delim = "~" if fmt == "x12" else "\\'"
            elem_delim = "*" if fmt == "x12" else "+"

            segments = parsed.get("segments", [])
            segment_ids = [seg["segment_id"] for seg in segments]

            missing = []
            for error in errors:
                if error.field == "segments" and "missing" in error.description.lower():
                    seg_name = error.expected.split("\\'")[1] if "\\'" in error.expected else ""
                    if seg_name and seg_name not in segment_ids:
                        missing.append(seg_name)

            corrected = [elem_delim.join(seg["elements"]) for seg in segments]

            templates = {
                "ISA": f"ISA{elem_delim}00{elem_delim}          {elem_delim}00",
                "GS": f"GS{elem_delim}PO{elem_delim}SENDER{elem_delim}RECEIVER",
                "ST": f"ST{elem_delim}850{elem_delim}0001",
                "SE": f"SE{elem_delim}10{elem_delim}0001",
                "GE": f"GE{elem_delim}1{elem_delim}1",
                "IEA": f"IEA{elem_delim}1{elem_delim}000000001",
            }

            for seg in missing:
                if seg in templates:
                    if seg in ["ISA", "UNB"]:
                        corrected.insert(0, templates[seg])
                    elif seg in ["GS"]:
                        corrected.insert(min(1, len(corrected)), templates[seg])
                    elif seg in ["ST", "UNH"]:
                        corrected.insert(min(2, len(corrected)), templates[seg])
                    else:
                        corrected.append(templates[seg])

            return delim.join(corrected) + delim

        return original
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/services/zpl_parser.py
# ══════════════════════════════════════════════════════════════
FILES["app/services/zpl_parser.py"] = '''import re
from typing import Dict, Any


def parse_zpl_script(script: str) -> Dict[str, Any]:
    parsed = {}

    fd_blocks = re.findall(r"\\^FD(.*?)\\^FS", script, re.DOTALL)
    clean_blocks = [block.strip() for block in fd_blocks if block.strip()]

    tracking_patterns = [
        r"\\b[A-Z]{2}\\d{18,22}\\b",
        r"\\b1Z[A-Z0-9]{16}\\b",
        r"\\b\\d{12,22}\\b",
        r"\\b[A-Z]{4}\\d{10,}\\b",
    ]
    for pattern in tracking_patterns:
        for block in clean_blocks:
            match = re.search(pattern, block)
            if match:
                parsed["tracking_number"] = match.group(0)
                parsed["barcode"] = match.group(0)
                break
        if "tracking_number" in parsed:
            break

    postal_patterns = [
        r"\\b\\d{5}(-\\d{4})?\\b",
        r"\\b[A-Z]\\d[A-Z]\\s?\\d[A-Z]\\d\\b",
        r"\\b[A-Z]{1,2}\\d{1,2}\\s?\\d[A-Z]{2}\\b",
        r"\\b\\d{4,6}\\b",
    ]
    for pattern in postal_patterns:
        for block in clean_blocks:
            match = re.search(pattern, block)
            if match:
                parsed["postal_code"] = match.group(0)
                break
        if "postal_code" in parsed:
            break

    weight_pattern = r"\\b\\d+(\\.\\d+)?\\s?(KG|LB|kg|lb|G|g|OZ|oz)\\b"
    for block in clean_blocks:
        match = re.search(weight_pattern, block)
        if match:
            parsed["weight"] = match.group(0)
            break

    for block in clean_blocks:
        cc_match = re.match(r"^[A-Z]{2}$", block.strip())
        if cc_match:
            parsed["country_code"] = cc_match.group(0)
            break

    service_pattern = r"\\b(EXPRESS|STANDARD|PRIORITY|ECONOMY|OVERNIGHT|GROUND|NEXT\\s?DAY)\\b"
    for block in clean_blocks:
        match = re.search(service_pattern, block, re.IGNORECASE)
        if match:
            parsed["service_type"] = match.group(0).upper()
            break

    address_blocks = []
    temp_block = []
    for block in clean_blocks:
        if len(block.split()) >= 2:
            temp_block.append(block)
        else:
            if len(temp_block) >= 3:
                address_blocks.append(temp_block)
            temp_block = []
    if len(temp_block) >= 3:
        address_blocks.append(temp_block)

    if len(address_blocks) >= 1:
        parsed["sender_block"] = address_blocks[0]
    if len(address_blocks) >= 2:
        parsed["recipient_block"] = address_blocks[1]

    if "^BC" in script:
        parsed["barcode_type"] = "CODE128"
    elif "^BX" in script:
        parsed["barcode_type"] = "DATAMATRIX"
    elif "^BQ" in script:
        parsed["barcode_type"] = "QR"
    elif "^BA" in script:
        parsed["barcode_type"] = "CODE39"
    elif "^B2" in script:
        parsed["barcode_type"] = "INTERLEAVED2OF5"

    return parsed
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/utils/__init__.py
# ══════════════════════════════════════════════════════════════
FILES["app/utils/__init__.py"] = ''

# ══════════════════════════════════════════════════════════════
# FILE: app/utils/file_handler.py
# ══════════════════════════════════════════════════════════════
FILES["app/utils/file_handler.py"] = '''import os
import uuid
from pathlib import Path
from fastapi import UploadFile


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def save_upload_file(upload_file: UploadFile, prefix: str = "") -> str:
    file_extension = Path(upload_file.filename).suffix
    unique_filename = f"{prefix}_{uuid.uuid4()}{file_extension}"
    file_path = UPLOAD_DIR / unique_filename

    with open(file_path, "wb") as f:
        content = await upload_file.read()
        f.write(content)

    return str(file_path)


def read_file_content(file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        return f.read()


def read_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()
'''

# ══════════════════════════════════════════════════════════════
# FILE: app/utils/pdf_extractor.py
# ══════════════════════════════════════════════════════════════
FILES["app/utils/pdf_extractor.py"] = '''import pdfplumber
from typing import Dict, Any, Tuple
import re


def extract_structured_pdf_data(pdf_path: str) -> Dict[str, Any]:
    raw_text = ""
    text_blocks = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            raw_text += page_text + "\\n"

            words = page.extract_words()
            for word in words:
                text_blocks.append({
                    "text": word["text"],
                    "bbox": [word["x0"], word["top"], word["x1"], word["bottom"]]
                })

    is_text_based = len(raw_text.strip()) > 50

    return {
        "raw_text": raw_text,
        "text_blocks": text_blocks,
        "metadata": {"is_text_based": is_text_based}
    }


def generate_rule_template_from_spec(
    spec_data: Dict[str, Any],
    spec_type: str
) -> Tuple[Dict[str, Any], float]:

    raw_text = spec_data.get("raw_text", "")
    text_blocks = spec_data.get("text_blocks", [])
    raw_text_upper = raw_text.upper()

    rules = {
        "required_fields": [],
        "field_formats": {},
        "layout_constraints": {},
        "validation_patterns": {}
    }

    field_score = 0
    pattern_score = 0
    layout_score = 0

    if spec_type == "label":
        # Tracking Number
        tracking_regex = re.search(
            r"tracking\\s*number.*?(\\d{1,2})\\s*[-to]{0,3}\\s*(\\d{1,2})?\\s*(alphanumeric|numeric)?",
            raw_text, re.IGNORECASE
        )
        if tracking_regex:
            min_len = tracking_regex.group(1)
            max_len = tracking_regex.group(2) or min_len
            rules["field_formats"]["tracking_number"] = {
                "pattern": f"^[A-Z0-9]{{{min_len},{max_len}}}$",
                "required": True
            }
            rules["required_fields"].append("tracking_number")
            field_score += 1
            pattern_score += 1

        # Shipment Number
        shipment_regex = re.search(
            r"(?:shipment|consignment|airwaybill|awb)\\s*(?:number|id|identifier).*?(\\d{1,2})\\s*[-to]{0,3}\\s*(\\d{1,2})?",
            raw_text, re.IGNORECASE
        )
        if shipment_regex:
            min_len = shipment_regex.group(1)
            max_len = shipment_regex.group(2) or min_len
            rules["field_formats"]["shipment_number"] = {
                "pattern": f"^[A-Z0-9]{{{min_len},{max_len}}}$",
                "required": True
            }
            rules["required_fields"].append("shipment_number")
            field_score += 1
            pattern_score += 1

        # Barcode
        barcode_types = ["CODE128", "CODE 128", "QR", "PDF417", "DATAMATRIX",
                         "DATA MATRIX", "EAN128", "EAN-128", "GS1-128",
                         "INTERLEAVED", "ITF", "CODE39"]
        for barcode in barcode_types:
            if barcode in raw_text_upper:
                rules["field_formats"]["barcode"] = {
                    "format": barcode.replace(" ", "").replace("-", ""),
                    "required": True
                }
                rules["required_fields"].append("barcode")
                field_score += 1
                pattern_score += 1
                break

        # Postal Code
        if "POSTAL" in raw_text_upper or "ZIP" in raw_text_upper or "POSTCODE" in raw_text_upper:
            postal_pattern = r"^\\d{5}(-\\d{4})?$"
            if re.search(r"[A-Z]\\d[A-Z]\\s?\\d[A-Z]\\d", raw_text):
                postal_pattern = r"^[A-Z]\\d[A-Z]\\s?\\d[A-Z]\\d$"
            elif re.search(r"[A-Z]{1,2}\\d{1,2}\\s?\\d[A-Z]{2}", raw_text):
                postal_pattern = r"^[A-Z]{1,2}\\d{1,2}\\s?\\d[A-Z]{2}$"

            rules["field_formats"]["postal_code"] = {
                "pattern": postal_pattern,
                "required": True
            }
            rules["required_fields"].append("postal_code")
            field_score += 1
            pattern_score += 1

        # Weight
        if re.search(r"(?:weight|gross\\s*weight|actual\\s*weight)", raw_text, re.IGNORECASE):
            rules["field_formats"]["weight"] = {
                "pattern": r"^\\d+(\\.\\d+)?\\s?(KG|LB|kg|lb|G|g)$",
                "required": True
            }
            rules["required_fields"].append("weight")
            field_score += 1

        # Country Code
        if re.search(r"(?:country\\s*code|destination\\s*country|iso\\s*3166)", raw_text, re.IGNORECASE):
            rules["field_formats"]["country_code"] = {
                "pattern": r"^[A-Z]{2}$",
                "required": True
            }
            rules["required_fields"].append("country_code")
            field_score += 1

        # Service Type
        if re.search(r"(?:service\\s*(?:type|code|indicator)|product\\s*(?:code|type))", raw_text, re.IGNORECASE):
            rules["field_formats"]["service_type"] = {
                "pattern": r"^[A-Z0-9]{1,5}$",
                "required": True
            }
            rules["required_fields"].append("service_type")
            field_score += 1

        # Layout Size
        size_match = re.search(r"(\\d+)\\s*[xX]\\s*(\\d+)\\s*(mm|cm|inch|in|\\")?", raw_text)
        if size_match:
            rules["layout_constraints"] = {
                "label_width": int(size_match.group(1)),
                "label_height": int(size_match.group(2)),
                "units": (size_match.group(3) or "inches").replace(\\'"\\', \\'inches\\').replace(\\'in\\', \\'inches\\')
            }
            layout_score += 1

        if len(text_blocks) > 20:
            layout_score += 0.5

        field_conf = min(field_score / 5, 1.0)
        pattern_conf = min(pattern_score / 5, 1.0)
        layout_conf = min(layout_score / 1.5, 1.0)
        confidence_score = round(0.4 * field_conf + 0.4 * pattern_conf + 0.2 * layout_conf, 2)

    elif spec_type == "edi":
        rules["required_segments"] = []
        standard_x12 = ["ISA", "GS", "ST", "SE", "GE", "IEA"]
        edifact_segs = ["UNB", "UNH", "UNT", "UNZ", "BGM", "DTM"]

        for seg in standard_x12:
            if seg in raw_text_upper:
                rules["required_segments"].append(seg)

        for seg in edifact_segs:
            if seg in raw_text_upper and seg not in rules["required_segments"]:
                rules["required_segments"].append(seg)

        if any(s in rules["required_segments"] for s in ["ISA", "GS", "ST"]):
            rules["format_type"] = "x12"
            rules["delimiter_rules"] = {
                "segment_delimiter": "~",
                "element_delimiter": "*",
                "sub_element_delimiter": ":"
            }
        elif any(s in rules["required_segments"] for s in ["UNB", "UNH"]):
            rules["format_type"] = "edifact"
            rules["delimiter_rules"] = {
                "segment_delimiter": "\\'",
                "element_delimiter": "+",
                "sub_element_delimiter": ":"
            }

        rules["segment_order"] = rules["required_segments"] or standard_x12

        rules["required_fields"] = []
        edi_fields = [
            "sender_id", "receiver_id", "interchange_control",
            "transaction_set", "purchase_order", "invoice_number"
        ]
        for field in edi_fields:
            if field.replace("_", " ").upper() in raw_text_upper:
                rules["required_fields"].append(field)

        all_segments = standard_x12 + edifact_segs
        confidence_score = round(
            min(len(rules["required_segments"]) / max(len(all_segments) / 2, 1), 1.0), 2
        )
    else:
        confidence_score = 0.0

    return rules, confidence_score
'''


# ══════════════════════════════════════════════════════════════
# AUTO-SPLITTER: Run this file to create all project files
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  CARRIER LABEL & EDI VALIDATOR - FILE GENERATOR")
    print("=" * 60)
    print()

    created = 0
    for filepath, content in FILES.items():
        # Create directories
        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        # Write file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        created += 1
        print(f"  Created: {filepath}")

    # Create uploads directory
    os.makedirs("uploads", exist_ok=True)
    print(f"  Created: uploads/")

    print()
    print(f"  Total files created: {created}")
    print()
    print("  NEXT STEPS:")
    print("  1. Copy .env.example to .env and fill in your credentials")
    print("  2. pip install -r requirements.txt")
    print("  3. uvicorn app.main:app --reload --port 8000")
    print()
    print("=" * 60)
