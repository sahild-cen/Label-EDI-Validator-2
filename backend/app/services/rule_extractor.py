"""
11-Step Rule Extraction Pipeline (Two-Pass Architecture) with Learning Loop
============================================================================
Pass 0 (NEW):  Check for golden rules — if verified rules exist for this
               carrier, use them directly (skip extraction entirely)
Pass 1 (Steps 1-10): Extract candidate rules via Claude
Pass 1.5 (NEW): Sanity checks on extracted rules
Pass 2 (Step 10.5):  Validate & classify rules via Claude (with few-shot learning)
Step 11:             Output final validated rules
Post (NEW):    Offer to save validated rules as golden rules for next time

This architecture works for ANY carrier spec without
hardcoded field lists or keyword-based filtering.
"""

import re
from typing import List, Dict, Optional

from app.services.pdf_parser import (
    extract_text_from_pdf,
    chunk_text,
    detect_sections,
    filter_rule_sections
)
from app.services.claude_service import extract_rules_from_chunk
from app.services.rule_normalizer import normalize_rules
from app.services.rule_canonicalizer import (
    canonicalize_rules,
    get_golden_rules,
    save_golden_rules,
    load_learned_corrections,
)
from app.services.rule_merger import merge_rules_by_field
from app.services.rule_validator import (
    validate_rules_with_ai,
    sanity_check_rules,
    load_corrections,
)


RULE_KEYWORDS = [
    "barcode", "label", "postal code", "postcode", "tracking",
    "license plate", "routing", "field", "format", "mandatory",
    "required", "length", "must", "shall", "digit", "numeric",
    "alphanumeric", "encoding", "weight", "segment",
    "element", "edi", "shipment", "consignment", "address",
    "piece", "service", "product", "country", "code"
]

IGNORE_FIELD_KEYWORDS = [
    "iso", "standard", "specification", "example", "guide",
    "implementation", "document", "version", "copyright",
    "appendix", "annex", "glossary", "definition", "index"
]


def filter_rule_chunks(chunks):
    """Keep only chunks that likely contain validation rules."""
    filtered = [c for c in chunks if any(k in c.lower() for k in RULE_KEYWORDS)]
    return filtered if filtered else chunks


def filter_meta_rules(rules):
    """Remove rules with meta/structural field names (light filter only)."""
    return [
        r for r in rules
        if not any(k in r.get("field_name", r.get("field", "")).lower() for k in IGNORE_FIELD_KEYWORDS)
    ]


def deduplicate_rules(rules):
    """Remove duplicate rules by field_name."""
    seen = set()
    unique = []
    for rule in rules:
        name = rule.get("field_name", rule.get("field", "")).lower().strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(rule)
    return unique


def validate_regex_patterns(rules):
    """Reject impossible regex patterns before Pass 2."""
    cleaned = []
    for rule in rules:
        regex = rule.get("regex", "")
        if regex:
            try:
                re.compile(regex)
                quants = re.findall(r"\{(\d+),(\d+)\}", regex)
                for min_val, max_val in quants:
                    if int(min_val) > int(max_val):
                        rule["regex"] = ""
                        break
            except re.error:
                rule["regex"] = ""
        cleaned.append(rule)
    return cleaned


def init_learning(db=None):
    """
    Initialize the learning system. Call at app startup with your MongoDB db object.
    This loads past corrections, learned aliases, and golden rules into memory.
    """
    if db:
        load_learned_corrections(db)
        load_corrections(db)
        print("[Pipeline] Learning system initialized")


def extract_rules_from_pdf(file_path: str, carrier_name: str = "", db=None) -> List[Dict]:
    """
    Full pipeline with two-pass AI architecture and learning loop.

    NEW: Pass 0 checks for golden rules first.
    NEW: Post-extraction sanity checks catch bad rules early.
    NEW: Few-shot examples from corrections database improve Pass 2.

    Args:
        file_path: path to the carrier spec PDF
        carrier_name: carrier identifier (e.g., 'ups', 'dhl', 'fedex')
        db: MongoDB database object (optional, enables learning features)
    """

    # ═══ PASS 0: CHECK GOLDEN RULES ═══
    golden = get_golden_rules(carrier_name) if carrier_name else None
    if golden:
        print(f"\n[Pass 0] Found {len(golden)} golden rules for '{carrier_name}' — skipping extraction")
        print("[Pass 0] To re-extract, delete golden rules via the API")
        for r in golden:
            status = "REQUIRED" if r.get("required") else "optional"
            regex_status = f"regex={r['regex'][:30]}" if r.get("regex") else "no regex"
            print(f"  {r['field']} [{status}] ({regex_status})")
        return golden

    # ═══ PASS 1: EXTRACT CANDIDATE RULES ═══

    # Step 2: Extract raw text
    text = extract_text_from_pdf(file_path)
    print(f"[Pass 1] Step 2: Extracted {len(text)} characters")

    if len(text.strip()) < 50:
        print("[Pass 1] Very little text extracted from PDF")
        return []

    # Step 3: Detect sections
    sections = detect_sections(text)
    print(f"[Pass 1] Step 3: Detected {len(sections)} sections")

    # Step 4: Filter relevant sections
    rule_sections = filter_rule_sections(sections)
    print(f"[Pass 1] Step 4: {len(rule_sections)} relevant sections")

    all_rules = []

    for i, section in enumerate(rule_sections):
        section_text = "\n".join(section["content"])
        section_title = section.get("title", f"Section {i + 1}")

        if len(section_text.strip()) < 20:
            continue

        # Step 5: Split into chunks
        chunks = chunk_text(section_text)
        relevant_chunks = filter_rule_chunks(chunks)
        print(f"[Pass 1] Step 5: Section '{section_title}' -> {len(relevant_chunks)} chunks")

        for j, chunk_item in enumerate(relevant_chunks):
            # Step 6-7: Send to Claude & extract
            print(f"[Pass 1] Step 6-7: Chunk {j + 1}/{len(relevant_chunks)} [{section_title}]")
            rules = extract_rules_from_chunk(chunk_item, section_title=section_title)

            if rules:
                all_rules.extend(rules)
                print(f"  -> {len(rules)} candidate rules")
            else:
                print("  -> No rules")

    print(f"[Pass 1] Raw candidates: {len(all_rules)}")

    # Light meta filter
    filtered = filter_meta_rules(all_rules)
    print(f"[Pass 1] After meta filter: {len(filtered)}")

    # Deduplicate
    deduped = deduplicate_rules(filtered)
    print(f"[Pass 1] After dedup: {len(deduped)}")

    # Step 8: Normalize
    normalized = normalize_rules(deduped)
    print("[Pass 1] Step 8: Normalized")

    # Step 9: Canonicalize (with carrier context for regex corrections)
    canonical = canonicalize_rules(normalized, carrier_name=carrier_name)
    print("[Pass 1] Step 9: Canonicalized")

    # Step 10: Merge
    merged = merge_rules_by_field(canonical)
    print(f"[Pass 1] Step 10: Merged -> {len(merged)} candidate rules")

    # Validate regex before Pass 2
    regex_valid = validate_regex_patterns(merged)

    # ═══ PASS 1.5: SANITY CHECKS (NEW) ═══
    sane = sanity_check_rules(regex_valid, carrier_name=carrier_name)
    print(f"[Pass 1.5] Sanity checks: {len(regex_valid)} -> {len(sane)} candidates")

    # ═══ PASS 2: AI VALIDATION & CLASSIFICATION ═══
    print(f"\n[Pass 2] Starting AI validation of {len(sane)} candidate rules...")

    final_rules = validate_rules_with_ai(sane, carrier_name=carrier_name)

    # ═══ STEP 11: OUTPUT ═══
    print(f"\n[Pipeline] COMPLETE - {len(final_rules)} final validated rules")
    for r in final_rules:
        status = "REQUIRED" if r.get("required") else "optional"
        regex_status = f"regex={r['regex'][:30]}" if r.get("regex") else "no regex"
        print(f"  {r['field']} [{status}] ({regex_status})")

    # ═══ OFFER TO SAVE AS GOLDEN RULES ═══
    # In production, this would be triggered by a UI button after the user reviews
    # For now, we return the rules and the caller can save them
    if final_rules and carrier_name:
        print(f"\n[Pipeline] TIP: Call save_golden_rules(db, '{carrier_name}', rules) "
              f"to cache these as verified rules for next time")

    return final_rules


def force_reextract(carrier_name: str, db=None):
    """
    Clear golden rules for a carrier, forcing re-extraction on next upload.
    Useful when the carrier spec PDF has been updated.
    """
    if db:
        try:
            db.golden_rules.delete_one({"carrier": carrier_name.lower()})
            print(f"[Pipeline] Cleared golden rules for '{carrier_name}'")
        except Exception as e:
            print(f"[Pipeline] Warning: could not clear golden rules: {e}")