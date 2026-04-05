import io
import requests
from PIL import Image
from pdf2image import convert_from_bytes

def convert_to_image(file_bytes, filename):
    filename = filename.lower()

    # 1️⃣ ZPL → PNG using Labelary API
    if filename.endswith(".zpl"):
        url = "http://api.labelary.com/v1/printers/8dpmm/labels/4x6/0/"
        headers = {'Accept': 'image/png'}
        response = requests.post(url, headers=headers, data=file_bytes)

        if response.status_code == 200:
            return Image.open(io.BytesIO(response.content))
        else:
            raise Exception("ZPL conversion failed")

    # 2️⃣ PDF → PNG
    elif filename.endswith(".pdf"):
        images = convert_from_bytes(file_bytes)
        return images[0]  # first page only

    # 3️⃣ Image → Return directly
    elif filename.endswith((".png", ".jpg", ".jpeg")):
        return Image.open(io.BytesIO(file_bytes))

    else:
        raise Exception("Unsupported file type")
