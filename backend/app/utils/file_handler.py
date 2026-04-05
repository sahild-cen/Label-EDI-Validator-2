import os
import uuid
from pathlib import Path
from fastapi import UploadFile


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def save_upload_file(upload_file: UploadFile, prefix: str = "") -> str:
    file_extension = Path(upload_file.filename).suffix
    unique_filename = f"{prefix}_{uuid.uuid4()}{file_extension}"
    file_path = UPLOAD_DIR / unique_filename

    with open(file_path, "wb") as f:
        content = await upload_file.read()
        f.write(content)

    return str(file_path)


def read_file_content(file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        return f.read()


def read_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()