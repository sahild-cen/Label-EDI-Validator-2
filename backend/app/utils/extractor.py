import pytesseract
from pyzbar.pyzbar import decode

def extract_text(image):
    return pytesseract.image_to_string(image)

def extract_barcodes(image):
    barcodes = decode(image)
    return [barcode.data.decode("utf-8") for barcode in barcodes]
