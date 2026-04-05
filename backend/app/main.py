from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import carriers, validation
from app.routes.corrections import router as corrections_router
from app.routes.corrections import router as corrections_router


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
app.include_router(corrections_router)


@app.on_event("startup")
async def startup():
    """Initialize the learning system on app start."""
    try:
        from app.services.rule_extractor import init_learning
        from app.database import get_database
        db = get_database()
        init_learning(db)
        print("[Startup] Learning system initialized")
    except Exception as e:
        print(f"[Startup] Warning: Learning system init failed: {e}")
        print("[Startup] App will continue without learning features")


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