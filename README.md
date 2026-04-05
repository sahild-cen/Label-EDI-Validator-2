# Label & EDI Validation Tool

A complete full-stack specification-driven validation tool for shipping labels (ZPL/PNG/PDF) and EDI files (any format). The system is carrier-agnostic, modular, and production-ready (MVP level).

## Features

- Upload carrier specifications (PDF) to generate validation rule templates
- Validate shipping labels with OCR, barcode detection, and layout analysis
- Validate EDI files with automatic format detection (X12, EDIFACT, JSON, XML, delimited, fixed-width)
- Generate corrected ZPL and EDI scripts automatically
- Rule-template driven validation (no hardcoded carrier logic)
- Track validation history per carrier
- Beautiful, responsive UI built with React and Tailwind CSS

## Tech Stack

**Backend:**
- Python 3.9+
- FastAPI
- Supabase (PostgreSQL database)
- OpenCV (layout analysis)
- Tesseract OCR (text extraction)
- pyzbar (barcode detection)
- pdfplumber (PDF text extraction)

**Frontend:**
- React 18
- TypeScript
- Vite
- Tailwind CSS
- Lucide React (icons)

## Project Structure

```
label-edi-validator/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── main.py            # FastAPI application
│   │   ├── config.py          # Configuration
│   │   ├── database.py        # Supabase client
│   │   ├── models/            # Pydantic models
│   │   ├── routes/            # API routes
│   │   ├── services/          # Business logic
│   │   └── utils/             # Utility functions
│   ├── requirements.txt
│   └── README.md
│
├── frontend/                   # React frontend (current directory)
│   ├── src/
│   │   ├── components/        # Reusable components
│   │   ├── pages/             # Page components
│   │   ├── services/          # API service
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
└── README.md                  # This file
```

## Setup Instructions

### Prerequisites

1. **Node.js 18+** - For frontend development
2. **Python 3.9+** - For backend API
3. **Tesseract OCR** - For label text extraction
4. **Supabase Account** - For database

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

### 1. Database Setup

The Supabase database schema has already been created with the following tables:
- `carriers` - Store carrier information
- `carrier_specs` - Store uploaded specs and rule templates
- `validation_results` - Store validation history

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Edit .env and add your Supabase credentials:
# SUPABASE_URL=https://your-project.supabase.co
# SUPABASE_KEY=your-anon-key-here

# Start the backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at `http://localhost:8000`

API documentation at `http://localhost:8000/docs`

### 3. Frontend Setup

```bash
# Install dependencies
npm install

# Start the development server
npm run dev
```

Frontend will be available at `http://localhost:5173`

## Usage Guide

### Step 1: Upload Carrier Specifications

1. Navigate to the **Carrier Setup** page
2. Enter the carrier name (e.g., "DHL", "UPS", "FedEx")
3. Upload the Label Specification PDF (optional)
4. Upload the EDI Specification PDF (optional)
5. Click "Upload Carrier Specs"

The system will extract text from the PDFs and generate validation rule templates automatically.

### Step 2: Validate Files

1. Navigate to the **Validation Dashboard**
2. Select a carrier from the dropdown
3. Upload a label file (ZPL, PNG, JPG, or PDF)
   - Check "This is a ZPL file" if uploading a ZPL text file
4. Click "Validate Label"
5. Upload an EDI file (any text format)
6. Click "Validate EDI"

### Step 3: Review Results

The system will display:
- Validation status (PASS/FAIL)
- Compliance score percentage
- List of errors with detailed descriptions
- Corrected scripts (if errors found)
- Copy-to-clipboard buttons for corrected scripts

## What the System Validates

### Label Validation

- Field presence (tracking number, barcode, addresses)
- Barcode detection and format
- Layout structure and alignment
- Text extraction accuracy
- Required field formats

### EDI Validation

- Required segments presence
- Segment order compliance
- Field formats and patterns
- Structure compliance
- Delimiter correctness

## Validation Rules

All validation is rule-template driven. When you upload a carrier specification:

1. The system extracts text from the PDF
2. Generates a rule template with:
   - Required fields/segments
   - Field formats and patterns
   - Layout constraints
   - Validation patterns
3. Stores the template in the database
4. Uses the template for all future validations

**No carrier-specific logic is hardcoded** - the system is completely carrier-agnostic.

## Sample Test Files

Sample test files are available in the `test-data/` directory:

- `sample_label.zpl` - Sample ZPL label script
- `sample_edi_x12.txt` - Sample X12 EDI file
- `sample_edi_edifact.txt` - Sample EDIFACT EDI file
- `sample_label_spec.pdf` - Sample label specification
- `sample_edi_spec.pdf` - Sample EDI specification

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

## Development

### Run Frontend in Development Mode

```bash
npm run dev
```

### Run Backend in Development Mode

```bash
cd backend
uvicorn app.main:app --reload
```

### Build Frontend for Production

```bash
npm run build
```

### Type Checking

```bash
npm run typecheck
```

### Linting

```bash
npm run lint
```

## Troubleshooting

### Tesseract Not Found

If you get a "Tesseract not found" error:
- Ensure Tesseract is installed and in your PATH
- On macOS: `brew install tesseract`
- On Ubuntu: `sudo apt-get install tesseract-ocr`

### CORS Errors

If you get CORS errors:
- Ensure the backend is running on `http://localhost:8000`
- Check that the frontend API service uses the correct backend URL

### Database Connection Issues

If you get database connection errors:
- Verify your `.env` file has correct Supabase credentials
- Check that your Supabase project is active
- Ensure the database schema has been created

## Production Deployment

### Backend Deployment

1. Deploy to any Python hosting service (Railway, Render, Heroku, etc.)
2. Set environment variables for `SUPABASE_URL` and `SUPABASE_KEY`
3. Install Tesseract OCR on the server
4. Run with: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Frontend Deployment

1. Update `API_BASE_URL` in `src/services/api.ts` to your backend URL
2. Build: `npm run build`
3. Deploy the `dist/` folder to any static hosting (Vercel, Netlify, Cloudflare Pages, etc.)

## License

MIT

## Support

For issues and questions, please open a GitHub issue.
