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

        format_type = self.detect_format(edi_content)

        try:
            parsed_data = self.parse_content(edi_content, format_type)
        except Exception as e:
            errors.append(ValidationError(
                field="parsing",
                expected="Valid {} format".format(format_type),
                actual="Parse error",
                description="Failed to parse EDI content: {}".format(str(e))
            ))
            return {
                "status": "FAIL",
                "errors": [err.dict() for err in errors],
                "corrected_edi_script": None,
                "compliance_score": 0.0
            }

        required_segments = self.rules.get("required_segments", [])
        segment_order = self.rules.get("segment_order", [])

        if format_type in ["x12", "edifact"]:
            segments = parsed_data.get("segments", [])
            segment_ids = [seg["segment_id"] for seg in segments]

            for required_seg in required_segments:
                if required_seg not in segment_ids:
                    errors.append(ValidationError(
                        field="segments",
                        expected="Segment '{}' present".format(required_seg),
                        actual="Segment missing",
                        description="Required segment '{}' is missing".format(required_seg)
                    ))

            if segment_order:
                actual_indices = []
                for seg in segment_order:
                    if seg in segment_ids:
                        actual_indices.append(segment_ids.index(seg))

                if actual_indices != sorted(actual_indices):
                    order_str = ", ".join(segment_order)
                    actual_str = ", ".join(segment_ids[:5])
                    errors.append(ValidationError(
                        field="segment_order",
                        expected="Segments in order: {}".format(order_str),
                        actual="Actual order: {}...".format(actual_str),
                        description="Segments are not in the correct order"
                    ))

            # Validate element-level rules if present
            element_rules = self.rules.get("field_formats", {})
            for field_name, rule in element_rules.items():
                pattern = rule.get("pattern", "")
                required = rule.get("required", False)
                found = False
                for seg in segments:
                    for elem in seg.get("elements", []):
                        if pattern:
                            try:
                                if re.match(pattern, elem):
                                    found = True
                                    break
                            except re.error:
                                found = True
                                break
                    if found:
                        break
                if required and not found and pattern:
                    errors.append(ValidationError(
                        field=field_name,
                        expected="Element matching: {}".format(pattern),
                        actual="Not found in segments",
                        description="Required EDI element '{}' not found".format(field_name)
                    ))

        elif format_type == "json":
            required_fields = self.rules.get("required_fields", [])
            for field in required_fields:
                if field not in parsed_data:
                    errors.append(ValidationError(
                        field=field,
                        expected="Field '{}' present".format(field),
                        actual="Field missing",
                        description="Required field '{}' is missing".format(field)
                    ))

        denominator = max(
            len(required_segments or []) + len(self.rules.get("field_formats", {})) + 2, 1
        )
        compliance_score = max(0.0, 1.0 - (len(errors) / denominator))

        status = "PASS" if not errors else "FAIL"

        corrected_script = None
        if errors:
            corrected_script = self.generate_corrected_edi(
                edi_content, format_type, errors, parsed_data
            )

        return {
            "status": status,
            "errors": [e.dict() for e in errors],
            "corrected_edi_script": corrected_script,
            "compliance_score": compliance_score
        }

    def generate_corrected_edi(
        self,
        original: str,
        fmt: str,
        errors: List[ValidationError],
        parsed: Dict[str, Any]
    ) -> str:
        if fmt in ["x12", "edifact"]:
            delim = "~" if fmt == "x12" else "'"
            elem_delim = "*" if fmt == "x12" else "+"

            segments = parsed.get("segments", [])
            segment_ids = [seg["segment_id"] for seg in segments]

            missing = []
            for error in errors:
                if error.field == "segments" and "missing" in error.description.lower():
                    parts = error.expected.split("'")
                    seg_name = parts[1] if len(parts) > 1 else ""
                    if seg_name and seg_name not in segment_ids:
                        missing.append(seg_name)

            corrected = [elem_delim.join(seg["elements"]) for seg in segments]

            templates = {
                "ISA": "ISA{}00{}          {}00".format(elem_delim, elem_delim, elem_delim),
                "GS": "GS{}PO{}SENDER{}RECEIVER".format(elem_delim, elem_delim, elem_delim),
                "ST": "ST{}850{}0001".format(elem_delim, elem_delim),
                "SE": "SE{}10{}0001".format(elem_delim, elem_delim),
                "GE": "GE{}1{}1".format(elem_delim, elem_delim),
                "IEA": "IEA{}1{}000000001".format(elem_delim, elem_delim),
            }

            for seg in missing:
                if seg in templates:
                    if seg in ["ISA", "UNB"]:
                        corrected.insert(0, templates[seg])
                    elif seg == "GS":
                        corrected.insert(min(1, len(corrected)), templates[seg])
                    elif seg in ["ST", "UNH"]:
                        corrected.insert(min(2, len(corrected)), templates[seg])
                    else:
                        corrected.append(templates[seg])

            return delim.join(corrected) + delim

        return original