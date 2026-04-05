# Label & EDI Validation Tool - Backend

Python FastAPI backend for carrier-agnostic label and EDI validation.

## Prerequisites

- Python 3.9 or higher
- Tesseract OCR installed on your system
- Supabase account with database configured

### Install Tesseract OCR

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr
```

**Windows:**
Download and install from: https://github.com/UB-Mannheim/tesseract/wiki

## Setup Instructions

### 1. Create Virtual Environment

```bash
cd backend
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the `backend` directory:

```bash
cp .env.example .env
```

Edit `.env` and add your Supabase credentials:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here
LABELARY_API_URL=http://api.labelary.com/v1/printers/8dpmm/labels/4x6/0/
```

### 4. Run the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

API documentation available at `http://localhost:8000/docs`

## API Endpoints

### Carrier Management

- `POST /api/carriers/upload` - Upload carrier specifications
- `GET /api/carriers/list` - List all carriers
- `GET /api/carriers/{carrier_id}` - Get carrier details
- `DELETE /api/carriers/{carrier_id}` - Delete carrier

### Validation

- `POST /api/validate/label` - Validate shipping label
- `POST /api/validate/edi` - Validate EDI file
- `GET /api/validate/history/{carrier_id}` - Get validation history

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration settings
│   ├── database.py             # Supabase client
│   ├── models/                 # Pydantic models
│   │   ├── carrier.py
│   │   └── validation.py
│   ├── routes/                 # API routes
│   │   ├── carriers.py
│   │   └── validation.py
│   ├── services/               # Business logic
│   │   ├── spec_engine.py
│   │   ├── label_validator.py
│   │   ├── edi_validator.py
│   │   └── correction_engine.py
│   └── utils/                  # Utility functions
│       ├── file_handler.py
│       └── pdf_extractor.py
├── uploads/                    # Uploaded files (auto-created)
├── requirements.txt
└── README.md
```

## Testing the API

### 1. Upload Carrier Spec

```bash
curl -X POST "http://localhost:8000/api/carriers/upload" \
  -F "carrier_name=DHL" \
  -F "label_spec=@path/to/label_spec.pdf" \
  -F "edi_spec=@path/to/edi_spec.pdf"
```

### 2. Validate Label

```bash
curl -X POST "http://localhost:8000/api/validate/label" \
  -F "carrier_id=your-carrier-id" \
  -F "label_file=@path/to/label.png" \
  -F "is_zpl=false"
```

### 3. Validate EDI

```bash
curl -X POST "http://localhost:8000/api/validate/edi" \
  -F "carrier_id=your-carrier-id" \
  -F "edi_file=@path/to/edi_file.txt"
```

## Features

- Rule-template driven validation (no hardcoded carrier logic)
- Automatic format detection for EDI files (X12, EDIFACT, JSON, XML, delimited, fixed-width)
- ZPL rendering using Labelary API
- OCR text extraction with Tesseract
- Barcode detection with pyzbar
- Layout analysis with OpenCV
- Automatic correction script generation
- Validation history tracking

## Notes

- The system uses Supabase for data persistence
- Uploaded files are stored in the `uploads/` directory
- ZPL files are rendered to images using the Labelary API
- All validation is rule-driven based on uploaded carrier specifications
