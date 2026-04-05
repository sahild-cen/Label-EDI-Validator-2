from app.services.pdf_parser import extract_text_from_pdf, chunk_text
from app.services.claude_service import extract_rules_from_chunk

file_path = "uploads/DHL Label Spec.pdf"

text = extract_text_from_pdf(file_path)

chunks = chunk_text(text)

response = extract_rules_from_chunk(chunks[10])

print(response)