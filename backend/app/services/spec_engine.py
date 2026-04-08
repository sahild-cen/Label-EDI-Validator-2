from typing import Dict, Any
from datetime import datetime
from app.database import get_database
from app.utils.pdf_extractor import (
    extract_structured_pdf_data,
    generate_rule_template_from_spec
)


class SpecEngine:
    def __init__(self):
        self.db = get_database()

    # ----------------------------------------
    # PROCESS SPEC UPLOAD (VERSIONED SAVE)
    # ----------------------------------------
    async def process_spec_upload(
        self,
        carrier_name: str,
        label_spec_path: str = None,
        edi_spec_path: str = None
    ) -> Dict[str, Any]:

        label_rules = {}
        edi_rules = {}
        ai_extracted_rules = []

        # ──────── LABEL SPEC ────────
        if label_spec_path:
            # Path A: Structured extraction (regex-based)
            spec_data = extract_structured_pdf_data(label_spec_path)
            label_rules, structured_conf = generate_rule_template_from_spec(
                spec_data, spec_type="label"
            )
            final_confidence = structured_conf

            # Path B: AI extraction (Two-Pass Claude pipeline)
            try:
                from app.services.rule_extractor import extract_rules_from_pdf

                # Pass carrier_name so Pass 2 has context
                ai_rules = extract_rules_from_pdf(label_spec_path, carrier_name=carrier_name)

                if ai_rules:
                    ai_extracted_rules = ai_rules

                    # Merge AI-validated rules into field_formats
                    for rule in ai_rules:
                        field = rule.get("field", "")
                        if not field:
                            continue

                        # Add to field_formats (AI rules are already validated by Pass 2)
                        if "field_formats" not in label_rules:
                            label_rules["field_formats"] = {}

                        if field not in label_rules["field_formats"]:
                            label_rules["field_formats"][field] = {
                                "pattern": rule.get("regex", ""),
                                "required": rule.get("required", False),
                                "detect_by": rule.get("detect_by", ""),
                                "description": rule.get("description", "")
                            }
                        else:
                            # Merge: prefer AI regex if structured didn't find one
                            existing = label_rules["field_formats"][field]
                            if not existing.get("pattern") and rule.get("regex"):
                                existing["pattern"] = rule["regex"]
                            if rule.get("description") and not existing.get("description"):
                                existing["description"] = rule["description"]
                            if rule.get("detect_by") and not existing.get("detect_by"):
                                existing["detect_by"] = rule["detect_by"]

                        if rule.get("required") and field:
                            if field not in label_rules.get("required_fields", []):
                                label_rules.setdefault("required_fields", []).append(field)

                    # Boost confidence based on AI validated rules
                    if len(ai_rules) >= 3:
                        final_confidence = min(
                            0.5 * structured_conf + 0.5 * min(len(ai_rules) / 10, 1.0),
                            1.0
                        )

                    print("AI extracted and validated {} rules for {}".format(
                        len(ai_rules), carrier_name
                    ))

            except Exception as e:
                print("AI extraction failed (continuing with structured): {}".format(e))

            # Path C: ML fallback if confidence still low
            if final_confidence < 0.6:
                try:
                    from app.services.ml_fallback.layout_engine import run_layout_fallback
                    ml_rules, ml_conf, _ = run_layout_fallback(
                        spec_data.get("image_bytes")
                    )
                    if isinstance(ml_rules, dict):
                        label_rules.update(ml_rules)
                    final_confidence = 0.6 * final_confidence + 0.4 * ml_conf
                except Exception as e:
                    print("ML fallback failed: {}".format(e))

            label_rules["confidence_score"] = round(final_confidence, 2)

        # ──────── EDI SPEC ────────
        if edi_spec_path:
            spec_data = extract_structured_pdf_data(edi_spec_path)
            edi_rules, edi_conf = generate_rule_template_from_spec(
                spec_data, spec_type="edi"
            )

            try:
                from app.services.rule_extractor import extract_rules_from_pdf
                edi_ai_rules = extract_rules_from_pdf(edi_spec_path, carrier_name=carrier_name)
                if edi_ai_rules:
                    for rule in edi_ai_rules:
                        field = rule.get("field", "")
                        if field and rule.get("regex"):
                            edi_rules.setdefault("field_formats", {})[field] = {
                                "pattern": rule.get("regex", ""),
                                "required": rule.get("required", False),
                                "description": rule.get("description", "")
                            }
                    edi_conf = min(
                        0.5 * edi_conf + 0.5 * min(len(edi_ai_rules) / 8, 1.0), 1.0
                    )
            except Exception as e:
                print("EDI AI extraction failed: {}".format(e))

            edi_rules["confidence_score"] = round(edi_conf, 2)

        # ──────── VERSION HANDLING ────────
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

        # ──────── SAVE TO MONGO ────────
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

    # ----------------------------------------
    # GET ACTIVE RULE VERSION
    # ----------------------------------------
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

    # ----------------------------------------
    # ROLLBACK
    # ----------------------------------------
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
            "message": "Rolled back to version {}".format(version),
            "active_version": version
        }

    # ----------------------------------------
    # LIST VERSIONS
    # ----------------------------------------
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

    # ----------------------------------------
    # COMPARE VERSIONS
    # ----------------------------------------
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

    # ----------------------------------------
    # SIMULATE VALIDATION
    # ----------------------------------------
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
            "version_1": version_1,
            "version_2": version_2,
            "results": {"v1": result_v1, "v2": result_v2},
        }