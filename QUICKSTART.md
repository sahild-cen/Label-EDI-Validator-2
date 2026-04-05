# Quick Start Guide

Get the Label & EDI Validation Tool running in 5 minutes!

## Prerequisites Check

Before starting, ensure you have:

- [ ] Node.js 18+ installed (`node --version`)
- [ ] Python 3.9+ installed (`python --version`)
- [ ] Tesseract OCR installed
- [ ] Supabase account created

## Step-by-Step Setup

### 1. Install Tesseract OCR

Choose your operating system:

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
```

**Windows:**
Download from: https://github.com/UB-Mannheim/tesseract/wiki

Verify installation:
```bash
tesseract --version
```

### 2. Setup Backend (5 steps)

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
```

Now edit `backend/.env` and add your Supabase credentials:
<!-- ```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here
LABELARY_API_URL=http://api.labelary.com/v1/printers/8dpmm/labels/4x6/0/ -->
```

### 3. Setup Frontend (2 steps)

Open a new terminal window:

```bash
# Install dependencies
npm install

# That's it! Frontend is ready
```

### 4. Start Both Servers

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate  # Activate venv if not already active
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
npm run dev
```

### 5. Access the Application

Open your browser:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## First Steps

### Upload a Carrier

1. Go to **Carrier Setup** page
2. Enter carrier name: "Test Carrier"
3. Upload sample specs from `test-data/` (optional for testing)
4. Click "Upload Carrier Specs"

### Validate Files

1. Go to **Validation Dashboard**
2. Select your carrier
3. Upload test files from `test-data/`:
   - `sample_label.zpl` for label validation
   - `sample_edi_x12.txt` for EDI validation
4. Click validate buttons
5. Review results and corrected scripts

## Troubleshooting

### "Tesseract not found"
- Ensure Tesseract is installed and in your PATH
- Restart your terminal after installation

### "Connection refused" on frontend
- Make sure backend is running on port 8000
- Check backend terminal for errors

### "Database connection error"
- Verify `.env` file has correct Supabase credentials
- Check Supabase project is active

### "Module not found" errors in Python
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt` again

## What to Test

1. **Create a carrier** with specification PDFs
2. **Upload a ZPL label** and see OCR + barcode detection
3. **Upload an EDI file** and see auto-format detection
4. **Review errors** and compliance scores
5. **Copy corrected scripts** using the copy buttons

## Next Steps

- Read the full README.md for detailed information
- Check API documentation at http://localhost:8000/docs
- Review sample test files in `test-data/`
- Customize validation rules by uploading real carrier specs

## Need Help?

1. Check the main README.md
2. Review backend/README.md for API details
3. Check test-data/README.md for test file examples
4. Open an issue on GitHub

## Development Tips

**Hot Reload is Enabled:**
- Frontend: Changes auto-refresh in browser
- Backend: Changes auto-restart the API server

**Useful Commands:**
```bash
npm run lint          # Check code quality
npm run typecheck     # TypeScript validation
npm run build         # Production build
```

## Production Deployment

When ready to deploy:

1. Build frontend: `npm run build`
2. Deploy `dist/` folder to static hosting
3. Deploy backend to Python hosting service
4. Update API_BASE_URL in frontend to production backend URL

---

**You're all set!** Start validating labels and EDI files with confidence.
