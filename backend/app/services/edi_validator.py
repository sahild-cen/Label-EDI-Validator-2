import re
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

        if "'" in content and "+" in content:
            return "edifact"

        if "\n" in content and len(content.split("\n")) > 1:
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
            lines = content.strip().split("\n")
            return {"lines": lines, "segments": [line.split("|") for line in lines]}

        else:
            return {"raw_content": content}

    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        result = {}
        for child in element:
            child_data = child.text if child.text and not list(child) else self._xml_to_dict(child)
            result[child.tag] = child_data
        return result

    def _parse_edi_segments(self, content: str, format_type: str) -> Dict[str, Any]:
        if format_type == "x12":
            seg_delim, elem_delim = "~", "*"
        else:
            # EDIFACT: handle UNA service string advice
            seg_delim, elem_delim = "'", "+"

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

        # ── Step 1: Detect format ──
        format_type = self.detect_format(edi_content)

        print("\n" + "=" * 70)
        print("EDI VALIDATION — TERMINAL DEBUG OUTPUT")
        print("=" * 70)
        print(f"\n📄 EDI Content Preview (first 300 chars):")
        print(f"   {edi_content[:300]}...")
        print(f"\n🔍 Detected Format: {format_type}")

        # ── Step 2: Parse content ──
        try:
            parsed_data = self.parse_content(edi_content, format_type)
        except Exception as e:
            print(f"\n❌ PARSE ERROR: {str(e)}")
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
                "compliance_score": 0.0,
            }

        # ── Step 3: Log parsed segments ──
        if format_type in ["x12", "edifact"]:
            segments = parsed_data.get("segments", [])
            segment_ids = [seg["segment_id"] for seg in segments]

            print(f"\n📦 Parsed Segments ({len(segments)} total):")
            for seg in segments:
                sid = seg["segment_id"]
                elems = seg["elements"]
                preview = "+".join(elems[:5])
                if len(elems) > 5:
                    preview += f"... (+{len(elems) - 5} more)"
                print(f"   [{sid:6s}] {preview}")

            print(f"\n📋 Segment IDs found: {segment_ids}")
        else:
            segment_ids = []
            print(f"\n📦 Parsed Data Keys: {list(parsed_data.keys()) if isinstance(parsed_data, dict) else 'N/A'}")

        # ── Step 4: Load rules ──
        required_segments = self.rules.get("required_segments", [])
        segment_order = self.rules.get("segment_order", [])
        required_fields = self.rules.get("required_fields", [])
        delimiter_rules = self.rules.get("delimiter_rules", {})

        print(f"\n{'─' * 70}")
        print("📜 RULES FROM JSON (what we're validating against):")
        print(f"{'─' * 70}")
        print(f"   Required Segments: {required_segments}")
        print(f"   Segment Order:     {segment_order}")
        print(f"   Required Fields:   {required_fields}")
        print(f"   Delimiter Rules:   {delimiter_rules}")
        print(f"   Format Type Rule:  {self.rules.get('format_type', 'not specified')}")

        # ── Step 5: Validate format-specific rules ──
        total_checks = 0
        passed_checks = 0

        if format_type in ["x12", "edifact"]:

            # ── 5a: Check required segments ──
            print(f"\n{'─' * 70}")
            print("✅ SEGMENT PRESENCE CHECKS:")
            print(f"{'─' * 70}")

            # Filter required segments to match the detected format
            # X12 segments: ISA, GS, ST, SE, GE, IEA
            # EDIFACT segments: UNA, UNB, UNH, UNT, UNZ, BGM, DTM, etc.
            x12_segments = {"ISA", "GS", "ST", "SE", "GE", "IEA"}
            edifact_segments = {"UNA", "UNB", "UNH", "UNT", "UNZ", "BGM", "DTM",
                                "NAD", "CTA", "COM", "TDT", "LOC", "RFF", "FTX",
                                "GID", "MEA", "DIM", "PCI", "GIN", "CNT"}

            for required_seg in required_segments:
                total_checks += 1

                # Skip segments that don't belong to the detected format
                seg_upper = required_seg.upper().replace(":", "")
                if format_type == "edifact" and seg_upper in x12_segments:
                    print(f"   ⏭️  '{required_seg}' — SKIPPED (X12 segment, file is EDIFACT)")
                    passed_checks += 1  # Don't penalize
                    continue
                elif format_type == "x12" and seg_upper in edifact_segments:
                    print(f"   ⏭️  '{required_seg}' — SKIPPED (EDIFACT segment, file is X12)")
                    passed_checks += 1  # Don't penalize
                    continue

                # Check if segment exists (handle UNA: prefix edge case)
                found = False
                for sid in segment_ids:
                    # Normalize: "UNA:" → "UNA", "UNB" → "UNB"
                    sid_clean = sid.rstrip(":").strip()
                    req_clean = required_seg.rstrip(":").strip()
                    if sid_clean.upper() == req_clean.upper():
                        found = True
                        break

                if found:
                    print(f"   ✅ '{required_seg}' — FOUND in EDI")
                    passed_checks += 1
                else:
                    print(f"   ❌ '{required_seg}' — MISSING from EDI")
                    errors.append(ValidationError(
                        field="segments",
                        expected=f"Segment '{required_seg}' present",
                        actual="Segment missing",
                        description=f"Required segment '{required_seg}' is missing",
                    ))

            # ── 5b: Check segment order ──
            if segment_order:
                total_checks += 1
                print(f"\n{'─' * 70}")
                print("📐 SEGMENT ORDER CHECK:")
                print(f"{'─' * 70}")

                # Only check order for segments that are actually present and
                # belong to the detected format
                relevant_order = []
                for seg in segment_order:
                    seg_upper = seg.upper().replace(":", "")
                    if format_type == "edifact" and seg_upper in x12_segments:
                        continue
                    if format_type == "x12" and seg_upper in edifact_segments:
                        continue
                    relevant_order.append(seg)

                # Build actual order of relevant segments
                actual_relevant = []
                for sid in segment_ids:
                    sid_clean = sid.rstrip(":").strip().upper()
                    for rel in relevant_order:
                        if sid_clean == rel.upper():
                            actual_relevant.append(rel)
                            break

                print(f"   Expected order (format-filtered): {relevant_order}")
                print(f"   Actual order (in file):           {actual_relevant}")

                # Check if the relative order is preserved
                order_correct = True
                last_idx = -1
                for seg in relevant_order:
                    if seg in actual_relevant:
                        idx = actual_relevant.index(seg)
                        if idx < last_idx:
                            order_correct = False
                            break
                        last_idx = idx

                if order_correct:
                    print(f"   ✅ Segment order is correct")
                    passed_checks += 1
                else:
                    print(f"   ❌ Segment order violation detected")
                    actual_preview = ", ".join(segment_ids[:10])
                    if len(segment_ids) > 10:
                        actual_preview += "..."
                    errors.append(ValidationError(
                        field="segment_order",
                        expected=f"Segments in order: {', '.join(relevant_order)}",
                        actual=f"Actual order: {actual_preview}",
                        description="Segments are not in the correct order",
                    ))

            # ── 5c: Check delimiter rules ──
            if delimiter_rules:
                print(f"\n{'─' * 70}")
                print("🔤 DELIMITER CHECKS:")
                print(f"{'─' * 70}")

                expected_seg_delim = delimiter_rules.get("segment_delimiter")
                expected_elem_delim = delimiter_rules.get("element_delimiter")
                expected_sub_delim = delimiter_rules.get("sub_element_delimiter")

                if expected_seg_delim:
                    total_checks += 1
                    actual_delim = "'" if format_type == "edifact" else "~"
                    if actual_delim == expected_seg_delim:
                        print(f"   ✅ Segment delimiter: '{actual_delim}' matches expected '{expected_seg_delim}'")
                        passed_checks += 1
                    else:
                        print(f"   ❌ Segment delimiter: '{actual_delim}' ≠ expected '{expected_seg_delim}'")
                        errors.append(ValidationError(
                            field="delimiters",
                            expected=f"Segment delimiter: '{expected_seg_delim}'",
                            actual=f"Found: '{actual_delim}'",
                            description="Segment delimiter mismatch",
                        ))

                if expected_elem_delim:
                    total_checks += 1
                    actual_delim = "+" if format_type == "edifact" else "*"
                    if actual_delim == expected_elem_delim:
                        print(f"   ✅ Element delimiter: '{actual_delim}' matches expected '{expected_elem_delim}'")
                        passed_checks += 1
                    else:
                        print(f"   ❌ Element delimiter: '{actual_delim}' ≠ expected '{expected_elem_delim}'")
                        errors.append(ValidationError(
                            field="delimiters",
                            expected=f"Element delimiter: '{expected_elem_delim}'",
                            actual=f"Found: '{actual_delim}'",
                            description="Element delimiter mismatch",
                        ))

        # ── 5d: Check required fields (for any format) ──
        if required_fields:
            print(f"\n{'─' * 70}")
            print("📋 REQUIRED FIELD CHECKS:")
            print(f"{'─' * 70}")

            edi_upper = edi_content.upper()
            for field in required_fields:
                total_checks += 1
                # Check if field name appears in content
                field_found = field.replace("_", " ").upper() in edi_upper or field.upper() in edi_upper
                if field_found:
                    print(f"   ✅ '{field}' — found in EDI content")
                    passed_checks += 1
                else:
                    print(f"   ❌ '{field}' — NOT found in EDI content")
                    errors.append(ValidationError(
                        field="fields",
                        expected=f"Field '{field}' present",
                        actual="Field missing",
                        description=f"Required field '{field}' is missing",
                    ))

        # ── Step 6: Calculate score ──
        if total_checks > 0:
            compliance_score = round((passed_checks / total_checks) * 100, 1)
        else:
            compliance_score = 100.0

        status = "PASS" if not errors else "FAIL"

        print(f"\n{'=' * 70}")
        print(f"EDI VALIDATION RESULT: {status}")
        print(f"Score: {compliance_score}% ({passed_checks}/{total_checks} checks passed)")
        print(f"Errors: {len(errors)}")
        if errors:
            for e in errors:
                print(f"   ❌ [{e.field}] {e.description}")
        print("=" * 70 + "\n")

        # ── Step 7: Generate corrected script ──
        corrected_script = None
        if errors:
            corrected_script = self._generate_corrected_script(
                edi_content, format_type, errors
            )

        return {
            "status": status,
            "errors": [err.dict() for err in errors],
            "corrected_edi_script": corrected_script,
            "compliance_score": compliance_score,
        }

    def _generate_corrected_script(
        self, original: str, format_type: str, errors: List[ValidationError]
    ) -> str:
        """
        Generate a corrected EDI script by adding missing segments.
        NOTE: This is a best-effort suggestion — not guaranteed to be correct.
        """
        corrected = original

        missing_segments = []
        for err in errors:
            if err.field == "segments" and "missing" in err.description.lower():
                # Extract segment name from description
                seg_match = re.search(r"segment '(\w+)'", err.description)
                if seg_match:
                    missing_segments.append(seg_match.group(1))

        if missing_segments and format_type in ["x12", "edifact"]:
            comment = "\n"
            if format_type == "edifact":
                # Add placeholder segments before UNT/UNZ
                additions = []
                for seg in missing_segments:
                    additions.append(f"{seg}+PLACEHOLDER'")
                placeholder_block = "\n".join(additions)

                # Try to insert before UNT
                if "UNT+" in corrected:
                    corrected = corrected.replace(
                        "UNT+",
                        f"{placeholder_block}\nUNT+",
                    )
                else:
                    corrected += f"\n{placeholder_block}"

            elif format_type == "x12":
                additions = []
                for seg in missing_segments:
                    additions.append(f"{seg}*PLACEHOLDER~")
                placeholder_block = "\n".join(additions)

                if "SE*" in corrected:
                    corrected = corrected.replace(
                        "SE*",
                        f"{placeholder_block}\nSE*",
                    )
                else:
                    corrected += f"\n{placeholder_block}"

        return corrected