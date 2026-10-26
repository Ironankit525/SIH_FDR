import io
import re
from datetime import date, datetime

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
                    text = ocr_page(page)
                parts.append(text)
        text = "\n".join(parts)
        method = "pdf_text_and_ocr" if used_ocr else "embedded_pdf_text"
    else:
        text = pytesseract.image_to_string(Image.open(io.BytesIO(data)), timeout=30)
        method = "tesseract_ocr"
    if not text.strip():
        raise ValueError("No readable text found. Upload a clearer document or request manual review.")
    return text[:200000], method


def pdf_text_layer(data):
    """The PDF's own selectable text, with no OCR. Empty for a scan."""
    with fitz.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc).strip()[:200000]


def ocr_text(data, content_type):
    """Tesseract over the image, or over every rendered page of a PDF, ignoring any text layer."""
    if content_type == "application/pdf":
        with fitz.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(ocr_page(page) for page in doc)
    else:
        text = pytesseract.image_to_string(Image.open(io.BytesIO(data)), timeout=30)
    return text.strip()[:200000]


def ocr_page(page):
    if page.rect.width * page.rect.height * 1.7 ** 2 > 20_000_000:
        raise ValueError("Page dimensions exceed OCR safety limit")
    pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7))
    if pix.width * pix.height > 20_000_000:
        raise ValueError("Page dimensions exceed OCR safety limit")
    return pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))), timeout=30)


# A hyphen separates label and value only beside whitespace, so a reference such as AMOUNT-007 is not a label.
SEP = r"(?:\s*:\s*|\s+-\s*|\s*-\s+)"
# Each field has a specific label and, where useful, a weaker fallback label.
PATTERNS = {
    "bank": (r"(?:Bank(?: Name)?)" + SEP + r"([^\n]+)", None),
    "number": (r"(?:FDR(?: Number| No\.?)?|Instrument (?:Number|No\.?))" + SEP + r"([A-Za-z0-9/_-]+)",
               r"Reference" + SEP + r"([A-Za-z0-9/_-]+)"),
    "depositor_name": (r"Depositor(?: Name)?" + SEP + r"([^\n]+)", r"Institution(?: Name)?" + SEP + r"([^\n]+)"),
    # Maturity and interest amounts are different figures from the principal.
    "amount": (r"(?<!Maturity )(?<!Interest )(?:Deposit Amount|Principal(?: Amount)?|Amount)" + SEP + r"(?:INR|Rs\.?|₹)?\s*([\d,]+(?:\.\d{1,2})?)", None),
    "issue_date": (r"(?:Issue Date|Date of Deposit)" + SEP + r"([\d/.-]+)", None),
    "maturity_date": (r"(?:Maturity Date|Date of Maturity)" + SEP + r"([\d/.-]+)", None),
    "rate": (r"(?:Rate of Interest|Interest Rate|ROI)" + SEP + r"([\d.]+)\s*%", None),
    "maturity_value": (r"Maturity (?:Value|Amount)" + SEP + r"(?:INR|Rs\.?|₹)?\s*([\d,]+(?:\.\d{1,2})?)", None),
    "lien": (r"(?:Lien(?: Marked)?(?: (?:in )?Favou?r of)?|Pledged (?:to|in favou?r of))" + SEP + r"([^\n]+)", None),
}


def parse_value(key, raw):
    value = raw.strip()
    if key in ("amount", "maturity_value", "rate"):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    if key.endswith("date"):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                pass
        return None
    return value or None


def candidates(text):
    """Distinct values per field, in document order, and whether only the fallback label matched."""
    found = {}
    for key, (primary, fallback) in PATTERNS.items():
        for pattern, is_fallback in ((primary, False), (fallback, True)):
            if not pattern:
                continue
            values = []
            for match in re.finditer(pattern, text, re.I):
                value = parse_value(key, match.group(1))
                if value is not None and value not in values:
                    values.append(value)
            if values:
                found[key] = (values, is_fallback)
                break
    return found


def plausible(key, value):
    if key in ("amount", "maturity_value"):
        return value >= 1000
    if key == "rate":
        return 0 < value < 20
    if key.endswith("date"):
        return 1980 <= int(value[:4]) <= date.today().year + 30
    return True


def structure(text, method):
    # Heuristic parser confidence: how clearly the text states each field. It does not measure authenticity.
    base = 0.9 if method == "embedded_pdf_text" else 0.7
    fields, confidence = {}, {}
    for key, (values, is_fallback) in candidates(text).items():
        score = base
        if is_fallback:
            score *= 0.85
        if len(values) > 1:
            score *= 0.4
        if not plausible(key, values[0]):
            score *= 0.5
        fields[key], confidence[key] = values[0], round(score, 2)
    return fields, confidence
