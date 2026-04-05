import fitz  # PyMuPDF

def extract_pdf_text_and_image(path: str):
    doc = fitz.open(path)
    page = doc[0]

    # Render image
    pix = page.get_pixmap(dpi=300)
    image_bytes = pix.tobytes("png")

    # Extract text blocks
    text_blocks = []
    blocks = page.get_text("blocks")
    for block in blocks:
        x0, y0, x1, y1, text, *_ = block
        clean = text.strip()
        if clean:
            text_blocks.append({
                "text": clean,
                "bbox": [x0, y0, x1, y1]
            })

    return {
        "image_bytes": image_bytes,
        "text_blocks": text_blocks
    }
