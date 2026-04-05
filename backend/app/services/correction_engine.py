from typing import Dict, Any, List


class CorrectionEngine:
    @staticmethod
    def apply_corrections(
        original_content: str,
        errors: List[Dict[str, Any]],
        content_type: str
    ) -> str:
        if content_type == "zpl":
            return CorrectionEngine._correct_zpl(original_content, errors)
        elif content_type == "edi":
            return CorrectionEngine._correct_edi(original_content, errors)
        return original_content

    @staticmethod
    def _correct_zpl(zpl_content: str, errors: List[Dict[str, Any]]) -> str:
        corrected = zpl_content

        for error in errors:
            field = error.get("field", "")

            if field == "barcode":
                if "^BC" not in corrected:
                    corrected = corrected.replace(
                        "^XA",
                        "^XA\n^FO50,50^BCN,100,Y,N,N^FD123456789^FS"
                    )

            elif field == "tracking_number":
                if "^FO" not in corrected or "tracking" not in corrected.lower():
                    corrected = corrected.replace(
                        "^XA",
                        "^XA\n^FO50,200^A0N,30,30^FDTRACKING: 1234567890^FS"
                    )

        return corrected

    @staticmethod
    def _correct_edi(edi_content: str, errors: List[Dict[str, Any]]) -> str:
        corrected = edi_content

        for error in errors:
            field = error.get("field", "")
            description = error.get("description", "")

            if "ISA" in description and "missing" in description.lower():
                if not corrected.startswith("ISA"):
                    corrected = "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *" + corrected

        return corrected
