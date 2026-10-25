import io
import re
from datetime import datetime

import pymupdf as fitz
import pytesseract
from PIL import Image


def extract_text(data, content_type):
    """OCR fallback is explicit and failures remain visible to the reviewer."""
    if content_type == "application/pdf":
        parts, used_ocr = [], False
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                text = page.get_text().strip()
                if len(text) < 25:
                    used_ocr = True
                    if page.rect.width * page.rect.height * 1.7 ** 2 > 20_000_000:
                        raise ValueError("Page dimensions exceed OCR safety limit")
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7))
                    if pix.width * pix.height > 20_000_000:
                        raise ValueError("Page dimensions exceed OCR safety limit")
                    text = pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))), timeout=30)
                parts.append(text)
        text = "\n".join(parts)
        method = "pdf_text_and_ocr" if used_ocr else "embedded_pdf_text"
    else:
        text = pytesseract.image_to_string(Image.open(io.BytesIO(data)), timeout=30)
        method = "tesseract_ocr"
    if not text.strip():
        raise ValueError("No readable text found. Upload a clearer document or request manual review.")
    return text[:200000], method


def structure(text, method):
    patterns = {
        "bank": r"(?:Bank(?: Name)?)\s*[:\-]\s*([^\n]+)",
        "number": r"(?:FDR(?: Number| No\.?)?|Instrument (?:Number|No\.?)|Reference)\s*[:\-]\s*([A-Za-z0-9/_-]+)",
        "depositor_name": r"(?:Depositor(?: Name)?|Institution(?: Name)?)\s*[:\-]\s*([^\n]+)",
        "amount": r"(?:Deposit Amount|Amount|Principal)\s*[:\-]\s*(?:INR|Rs\.?|₹)?\s*([\d,]+(?:\.\d{1,2})?)",
        "issue_date": r"(?:Issue Date|Date of Deposit)\s*[:\-]\s*([\d/.-]+)",
        "maturity_date": r"(?:Maturity Date|Date of Maturity)\s*[:\-]\s*([\d/.-]+)",
    }
    fields, confidence = {}, {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = match.group(1).strip()
        if key == "amount":
            value = float(value.replace(",", ""))
        if key.endswith("date"):
            parsed = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
                try:
                    parsed = datetime.strptime(value, fmt).date().isoformat()
                    break
                except ValueError:
                    pass
            if not parsed:
                continue
            value = parsed
        fields[key] = value
        # These are heuristic parser confidence scores, not calibrated authenticity probabilities.
        confidence[key] = 0.94 if method == "embedded_pdf_text" else 0.72
    return fields, confidence
