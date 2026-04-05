"""
Spec Matching API Endpoints
============================
Add these endpoints to your validation.py router.

Endpoints:
  POST /api/validate/detect-spec   — Parse label, detect best spec, return for confirmation
  POST /api/validate/label         — Updated to accept spec_id parameter
"""

# ──────────────────────────────────────────────────────
# Add these imports to your existing validation.py
# ──────────────────────────────────────────────────────
#
# from app.services.spec_matcher import match_spec_to_label, get_specs_for_carrier
# from app.services.zpl_parser import parse_zpl_script
#
# ──────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────
# ENDPOINT 1: Detect the correct spec for a label
# ──────────────────────────────────────────────────────
#
# Add this to your validation router:
#
# @router.post("/api/validate/detect-spec")
# async def detect_spec(label_file: UploadFile = File(...)):
#     """
#     Parse a label file, detect carrier/region signals,
#     and return the best-matching spec PDF for user confirmation.
#
#     Response:
#     {
#         "signals": {
#             "carrier": "ups",
#             "origin_country": "NL",
#             "destination_country": "ES",
#             "origin_region": "europe",
#             "destination_region": "europe",
#             "service_type": "UPS STANDARD",
#             "tracking_number": "1ZFA55786805965030",
#             "is_international": true
#         },
#         "best_match": {
#             "spec_name": "2024_UPS_GTL_-_Europe",
#             "file_path": "/path/to/spec.pdf",
#             "carrier": "ups",
#             "confidence": 0.95,
#             "match_reasons": ["carrier matches", "origin region matches", ...],
#             "region": "europe",
#             "is_best_match": true
#         },
#         "alternatives": [...],
#         "needs_confirmation": true,
#         "message": "Auto-detected: '2024_UPS_GTL_-_Europe' (confidence: 95%). ..."
#     }
#     """
#     # Read and parse label
#     content = await label_file.read()
#     script = content.decode("utf-8", errors="ignore")
#     parsed_label = parse_zpl_script(script)
#
#     # Match against available specs
#     result = match_spec_to_label(parsed_label)
#
#     return result
#
#
# ──────────────────────────────────────────────────────
# ENDPOINT 2: Get alternative specs for a carrier
# ──────────────────────────────────────────────────────
#
# @router.get("/api/validate/specs/{carrier_name}")
# async def get_carrier_specs(carrier_name: str):
#     """
#     Get all available spec PDFs for a carrier.
#     Used when user rejects the auto-selected spec.
#     """
#     specs = get_specs_for_carrier(carrier_name)
#     return {"carrier": carrier_name, "specs": specs}
#
#
# ──────────────────────────────────────────────────────
# UPDATED ENDPOINT 3: Validate label with confirmed spec
# ──────────────────────────────────────────────────────
#
# @router.post("/api/validate/label")
# async def validate_label(
#     carrier_id: str = Form(...),
#     label_file: UploadFile = File(...),
#     spec_name: str = Form(None),  # NEW: optional spec override
# ):
#     """
#     Validate a label against a carrier's rules.
#
#     If spec_name is provided, use that specific spec's rules.
#     Otherwise, auto-detect the best spec (backward compatible).
#     """
#     # ... existing validation logic ...
#     # Use spec_name to look up the correct rules set
#     pass


# ═══════════════════════════════════════════════════════════════
# COMPLETE IMPLEMENTATION — paste into your validation.py
# ═══════════════════════════════════════════════════════════════

DETECT_SPEC_IMPLEMENTATION = '''
@router.post("/api/validate/detect-spec")
async def detect_spec(label_file: UploadFile = File(...)):
    """Parse a label and detect the best-matching carrier spec PDF."""
    from app.services.spec_matcher import match_spec_to_label
    from app.services.zpl_parser import parse_zpl_script

    content = await label_file.read()
    script = content.decode("utf-8", errors="ignore")

    # Parse the label
    parsed_label = parse_zpl_script(script)

    if not parsed_label:
        return {
            "signals": {},
            "best_match": None,
            "alternatives": [],
            "needs_confirmation": True,
            "message": "Could not parse the label file. Please check the file format."
        }

    # Match against available specs
    result = match_spec_to_label(parsed_label)

    return result


@router.get("/api/validate/specs/{carrier_name}")
async def get_carrier_specs(carrier_name: str):
    """Get all available spec PDFs for a specific carrier."""
    from app.services.spec_matcher import get_specs_for_carrier

    specs = get_specs_for_carrier(carrier_name)
    return {"carrier": carrier_name, "specs": specs}
'''