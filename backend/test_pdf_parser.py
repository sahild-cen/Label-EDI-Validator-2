from app.services.pdf_parser import extract_text_from_pdf, chunk_text
# Replace with a real carrier PDF
file_path = "uploads/DHL Transport Label Specs  2 5 2.pdf"

text = extract_text_from_pdf(file_path)

print("TEXT LENGTH:", len(text))
print("FIRST 500 CHARACTERS:\n")
print(text[:500])

chunks = chunk_text(text)

print("\nTOTAL CHUNKS:", len(chunks))
print("\nFIRST CHUNK:\n")
print(chunks[0])