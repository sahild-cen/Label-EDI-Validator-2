from pathlib import Path
from app.services.rule_extractor import extract_rules_from_pdf

BASE_DIR = Path(__file__).resolve().parent

file_path = BASE_DIR / "uploads" / "DHL Label Spec.pdf"

rules = extract_rules_from_pdf(str(file_path))

print("\nFINAL RULES:\n")
print(rules)