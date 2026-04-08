# Label & EDI Validation Tool

A multi-carrier shipping label and EDI compliance validation tool that extracts validation rules from carrier specification PDFs and validates ZPL-format shipping labels against those rules.

## Overview

The system learns validation rules from carrier specification documents (UPS, DHL, FedEx, etc.) using a two-pass AI extraction pipeline, then validates shipping labels by checking whether required elements are present. It uses a feedback loop where user corrections improve future validations — no code changes needed.

### How It Works

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Carrier Spec │────▶│  AI Extraction   │────▶│  Rules stored   │
│   PDF        │     │  (Pass 1 + 2)    │     │  in MongoDB     │
└──────────────┘     └──────────────────┘     └────────┬────────┘
                                                       │
┌──────────────┐     ┌──────────────────┐              │
│  ZPL Label   │────▶│  Raw Extractor   │──────────────┤
│  File        │     │  (all data)      │              │
└──────────────┘     └──────────┬───────┘              │
                                │                      │
                     ┌──────────▼──────────────────────▼──┐
                     │     Validation Engine               │
                     │  (detect_by pattern matching)       │
                     │                                     │
                     │  For each rule:                     │
                     │    detect_by → find on label        │
                     │    found? → PASS                    │
                     │    missing + required? → FAIL       │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────┐
                     │   Results + Feedback    │
                     │   - Flag wrong errors   │
                     │   - Report missing      │
                     │     checks              │
                     │   - Corrections feed    │
                     │     back into rules     │
                     └─────────────────────────┘
```

## Tech Stack

- **Backend:** Python / FastAPI
- **Frontend:** React / TypeScript
- **Database:** MongoDB (via Motor async driver)
- **AI:** Claude API (Anthropic) for rule extraction from PDFs
- **Label Format:** ZPL (Zebra Programming Language)

## Project Structure

```
backend/
├── app/
│   ├── main.py                    # FastAPI app, CORS, router registration
│   ├── database.py                # MongoDB connection (Motor async)
│   ├── config.py                  # Environment settings
│   │
│   ├── models/
│   │   └── validation.py          # Pydantic models (ValidationError, etc.)
│   │
│   ├── routes/
│   │   ├── carriers.py            # Carrier CRUD, spec PDF upload
│   │   ├── validation.py          # Label validation endpoint
│   │   └── corrections.py         # User feedback/corrections API
│   │
│   ├── services/
│   │   ├── zpl_parser.py          # ZPL raw data extractor
│   │   ├── label_validator.py     # Validation engine (detect_by matching)
│   │   ├── claude_service.py      # AI client + Pass 1 extraction prompt
│   │   ├── rule_extractor.py      # Full extraction pipeline orchestrator
│   │   ├── rule_validator.py      # Pass 2 AI classification
│   │   ├── rule_normalizer.py     # Field name normalization
│   │   ├── rule_canonicalizer.py  # Field aliasing + golden rules
│   │   ├── rule_merger.py         # Deduplicate/merge extracted rules
│   │   ├── pdf_parser.py          # PDF text extraction + chunking
│   │   ├── spec_matcher.py        # Auto-detect carrier from label
│   │   └── edi_validator.py       # EDI file validation
│   │
│   └── utils/
│       └── file_handler.py        # File upload handling
│
frontend/
├── src/
│   ├── components/
│   │   ├── ValidationDashboard.tsx # Main validation UI
│   │   └── CarrierSetup.tsx       # Carrier management UI
│   └── services/
│       └── api.ts                 # Backend API client
```

## Key Architecture Concepts

### 1. Two-Pass AI Rule Extraction

When a carrier spec PDF is uploaded:

**Pass 1** extracts candidate rules from the PDF text. Each rule includes a `detect_by` field that tells the validator how to find the element on a ZPL label.

**Pass 2** classifies each candidate as `DATA_VALIDATION` (keep) or `SPEC_GUIDELINE` (discard). Only fields that are visible on the printed label survive.

### 2. detect_by Pattern Matching

Each rule in MongoDB includes a `detect_by` instruction:

| detect_by | What it does | Example |
|-----------|-------------|---------|
| `zpl_command:^BD` | ZPL command present in script | MaxiCode barcode |
| `barcode_data:^1Z` | Barcode data matches prefix | UPS tracking barcode |
| `text_prefix:DATE:` | Text block starts with prefix | Shipment date |
| `text_contains:phrase` | Text block contains phrase | International notice |
| `text_pattern:regex` | Text block matches regex | Routing code format |
| `text_exact:A\|B\|C` | Text block equals one of these | Documentation indicator |
| `graphic:GFA` | Graphic element present | Service icon |
| `spatial:ship_from` | Text in ship-from area | Sender address |
| `spatial:ship_to` | Text in ship-to area | Receiver address |

### 3. ZPL Raw Extractor

The ZPL parser extracts ALL data from the label without assumptions:

- **Text blocks** — every `^FD` value with x,y position and font size
- **Barcodes** — every `^BC`, `^BD`, `^B7` etc. with type and data
- **Graphics** — every `^GFA` with size
- **ZPL commands** — complete list of all commands in the script

No hardcoded field names. No carrier-specific logic. The validator uses detect_by to find what it needs in this raw data.

### 4. Presence-Only Validation

The system checks whether required elements are **present** on the label, not whether their content matches a specific regex. This avoids false failures from format mismatches across different label generators.

### 5. Feedback Loop (Corrections)

Users can submit two types of corrections:

- **"This error is wrong"** — stores in `false_positive_overrides`, suppresses the error in future validations
- **"Report missing check"** — injects the field directly into the carrier's active rules in MongoDB, checked on next validation

Corrections are also injected as few-shot examples into future AI extraction prompts, so the system learns over time.

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB 6+
- Claude API key (Anthropic)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your settings
```

**.env configuration:**

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=label_edi_validator
CLAUDE_ENDPOINT=https://your-endpoint
CLAUDE_DEPLOYMENT=your-deployment-name
CLAUDE_API_KEY=your-api-key
```

**Start the backend:**

```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`, backend at `http://localhost:8000`.

## Usage

### 1. Upload Carrier Spec

Navigate to the Carrier Setup page. Enter the carrier name (e.g., "UPS Europe") and upload the carrier's label specification PDF. The system extracts validation rules using the two-pass AI pipeline and stores them in MongoDB.

### 2. Validate a Label

Navigate to the Validation page. Upload a ZPL label file. The system auto-detects the carrier from the label content, matches it to the stored rules, and validates. Results show PASS/FAIL with details on each checked field.

### 3. Correct Errors

If validation produces a wrong error, click the flag button to suppress it. If the validator missed a required field, use "Report Missing Check" to add it. Corrections persist in MongoDB and apply to all future validations for that carrier.

## MongoDB Collections

| Collection | Purpose |
|-----------|---------|
| `carriers` | Carrier specs with extracted rules (versioned) |
| `validation_corrections` | Audit trail of all user corrections |
| `false_positive_overrides` | Fields to suppress per carrier |
| `mandatory_field_overrides` | User-added mandatory fields |

## API Endpoints

### Carriers
- `POST /api/carriers/upload` — Upload carrier spec PDF
- `GET /api/carriers` — List all carriers
- `DELETE /api/carriers/{id}` — Delete a carrier

### Validation
- `POST /api/validate/detect-spec` — Auto-detect carrier from label
- `POST /api/validate/label` — Validate a label against carrier rules

### Corrections
- `POST /api/corrections` — Submit a correction (wrong_error or missing_check)
- `GET /api/corrections` — List past corrections

## Design Principles

1. **No hardcoded carrier logic** — all rules come from PDFs and user feedback
2. **Learning over patching** — corrections in MongoDB, not code changes
3. **Presence over content** — check if fields exist, not their exact format
4. **Carrier-agnostic** — same pipeline works for UPS, DHL, FedEx, any carrier
5. **detect_by over field names** — match data patterns, not field name strings
6. **Surgical changes** — existing UI and structure preserved, features added minimally
