# Project Structure Overview

Complete file structure of the Label & EDI Validation Tool.

```
label-edi-validator/
│
├── README.md                           # Main project documentation
├── QUICKSTART.md                       # Quick start guide
├── PROJECT_STRUCTURE.md                # This file
├── package.json                        # Frontend dependencies
├── package-lock.json                   # Lock file
├── vite.config.ts                      # Vite configuration
├── tsconfig.json                       # TypeScript configuration
├── tsconfig.app.json                   # App-specific TS config
├── tsconfig.node.json                  # Node-specific TS config
├── tailwind.config.js                  # Tailwind CSS configuration
├── postcss.config.js                   # PostCSS configuration
├── eslint.config.js                    # ESLint configuration
├── index.html                          # HTML entry point
├── .env.example                        # Environment variables template
├── .gitignore                          # Git ignore rules
│
├── backend/                            # Python FastAPI Backend
│   ├── README.md                       # Backend documentation
│   ├── requirements.txt                # Python dependencies
│   ├── .env.example                    # Backend env template
│   ├── .gitignore                      # Backend git ignore
│   │
│   └── app/                            # Application code
│       ├── __init__.py
│       ├── main.py                     # FastAPI app entry point
│       ├── config.py                   # Configuration management
│       ├── database.py                 # Supabase client setup
│       │
│       ├── models/                     # Pydantic data models
│       │   ├── __init__.py
│       │   ├── carrier.py              # Carrier models
│       │   └── validation.py           # Validation models
│       │
│       ├── routes/                     # API route handlers
│       │   ├── __init__.py
│       │   ├── carriers.py             # Carrier endpoints
│       │   └── validation.py           # Validation endpoints
│       │
│       ├── services/                   # Business logic
│       │   ├── __init__.py
│       │   ├── spec_engine.py          # Spec processing
│       │   ├── label_validator.py      # Label validation
│       │   ├── edi_validator.py        # EDI validation
│       │   └── correction_engine.py    # Script correction
│       │
│       └── utils/                      # Utility functions
│           ├── __init__.py
│           ├── file_handler.py         # File operations
│           └── pdf_extractor.py        # PDF text extraction
│
├── src/                                # React Frontend
│   ├── main.tsx                        # React entry point
│   ├── App.tsx                         # Main App component
│   ├── index.css                       # Global styles
│   ├── vite-env.d.ts                   # Vite type definitions
│   │
│   ├── components/                     # Reusable components
│   │   └── Navigation.tsx              # Navigation bar
│   │
│   ├── pages/                          # Page components
│   │   ├── CarrierSetup.tsx            # Carrier setup page
│   │   └── ValidationDashboard.tsx     # Validation page
│   │
│   └── services/                       # API services
│       └── api.ts                      # API client
│
└── test-data/                          # Sample test files
    ├── README.md                       # Test data documentation
    ├── sample_label.zpl                # Sample ZPL label
    ├── sample_edi_x12.txt              # Sample X12 EDI
    └── sample_edi_edifact.txt          # Sample EDIFACT EDI
```

## Key Files Explained

### Frontend

**Core Application:**
- `src/App.tsx` - Main application with routing logic
- `src/main.tsx` - React application entry point
- `index.html` - HTML template

**Pages:**
- `src/pages/CarrierSetup.tsx` - Upload carrier specifications
- `src/pages/ValidationDashboard.tsx` - Validate labels and EDI files

**Components:**
- `src/components/Navigation.tsx` - Top navigation bar

**Services:**
- `src/services/api.ts` - API client with TypeScript interfaces

**Configuration:**
- `vite.config.ts` - Vite build configuration
- `tailwind.config.js` - Tailwind CSS setup
- `tsconfig.json` - TypeScript compiler options

### Backend

**Core Application:**
- `app/main.py` - FastAPI app with CORS and routes
- `app/config.py` - Environment configuration
- `app/database.py` - Supabase client

**Models:**
- `app/models/carrier.py` - Carrier data models
- `app/models/validation.py` - Validation result models

**Routes:**
- `app/routes/carriers.py` - Carrier management endpoints
- `app/routes/validation.py` - Validation endpoints

**Services (Business Logic):**
- `app/services/spec_engine.py` - PDF extraction and rule generation
- `app/services/label_validator.py` - Label validation with OCR
- `app/services/edi_validator.py` - EDI validation with format detection
- `app/services/correction_engine.py` - Generate corrected scripts

**Utilities:**
- `app/utils/file_handler.py` - File upload and reading
- `app/utils/pdf_extractor.py` - PDF text extraction

**Configuration:**
- `requirements.txt` - Python dependencies
- `.env.example` - Environment variables template

## Database Schema

Stored in Supabase PostgreSQL:

**Tables:**
1. `carriers` - Carrier information
2. `carrier_specs` - Uploaded specs and rule templates
3. `validation_results` - Validation history

All tables have Row Level Security (RLS) enabled.

## Technology Stack Summary

### Frontend
- React 18
- TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- Lucide React (icons)

### Backend
- Python 3.9+
- FastAPI (web framework)
- Supabase (database)
- OpenCV (image processing)
- Tesseract OCR (text extraction)
- pyzbar (barcode detection)
- pdfplumber (PDF processing)

### Infrastructure
- Supabase PostgreSQL database
- Labelary API (ZPL rendering)

## File Count

- **Backend Python files:** 16
- **Frontend TypeScript/TSX files:** 6
- **Configuration files:** 10
- **Documentation files:** 5
- **Test data files:** 4

**Total:** 41 files

## Lines of Code (Approximate)

- **Backend Python:** ~1,500 lines
- **Frontend TypeScript/React:** ~800 lines
- **Configuration:** ~200 lines
- **Documentation:** ~1,200 lines

**Total:** ~3,700 lines

## API Endpoints

### Carrier Management
- `POST /api/carriers/upload` - Upload specs
- `GET /api/carriers/list` - List carriers
- `GET /api/carriers/{carrier_id}` - Get carrier
- `DELETE /api/carriers/{carrier_id}` - Delete carrier

### Validation
- `POST /api/validate/label` - Validate label
- `POST /api/validate/edi` - Validate EDI
- `GET /api/validate/history/{carrier_id}` - Get history

### System
- `GET /` - API info
- `GET /health` - Health check
- `GET /docs` - Swagger documentation

## Validation Features

### Label Validation
- ZPL rendering to image
- OCR text extraction
- Barcode detection (multiple formats)
- Layout block analysis
- Field presence validation
- Format compliance checking
- Corrected ZPL generation

### EDI Validation
- Auto-format detection (X12, EDIFACT, JSON, XML, delimited, fixed-width)
- Segment presence validation
- Segment order validation
- Field format validation
- Structure compliance
- Corrected EDI generation

## Key Design Principles

1. **Carrier-Agnostic:** No hardcoded carrier logic
2. **Rule-Template Driven:** All validation based on uploaded specs
3. **Modular Architecture:** Clear separation of concerns
4. **Type-Safe:** TypeScript frontend, Pydantic backend
5. **Production-Ready:** Error handling, validation, security
6. **Scalable:** Clean structure for easy extension
7. **Developer-Friendly:** Comprehensive documentation

## Running the Application

**Development Mode:**
```bash
Backend:  uvicorn app.main:app --reload
Frontend: npm run dev
```

**Production Build:**
```bash
Frontend: npm run build
Backend:  uvicorn app.main:app
```

## Next Steps for Enhancement

1. Add authentication and user management
2. Implement file storage in Supabase Storage
3. Add more validation rules and patterns
4. Create admin dashboard
5. Add batch validation
6. Implement webhooks for integrations
7. Add more carrier-specific rule templates
8. Create validation rule editor UI
9. Add export functionality for reports
10. Implement real-time validation status updates
