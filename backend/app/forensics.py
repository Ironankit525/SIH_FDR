"""Document integrity indicators. Each one prompts inspection; none proves forgery."""
import io
from datetime import datetime, timedelta

import pymupdf as fitz
from PIL import Image

from .extraction import candidates, ocr_page, structure
from .matching import same_reference

EDITING_TOOLS = ("photoshop", "gimp", "illustrator", "inkscape", "canva", "ilovepdf", "smallpdf", "sejda", "pdfescape",
                 "pdf-xchange", "phantompdf", "foxit pdf editor", "nitro pro", "pdffiller", "dochub", "pdf candy")
CRITICAL_FIELDS = ("number", "amount", "issue_date", "maturity_date")
VERSION = 1


def signal(code, severity, detail):
    return {"code": code, "severity": severity, "detail": detail}


def editing_tool(*values):
    text = " ".join(v or "" for v in values).casefold()
    return next((tool for tool in EDITING_TOOLS if tool in text), None)


def pdf_date(value):
    value = (value or "").removeprefix("D:")[:14]
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def inspect(data, content_type, ocr=True):
    report = {"version": VERSION, "signals": [], "metadata": {}, "ocr_crosscheck": "not_run"}
    if content_type != "application/pdf":
        with Image.open(io.BytesIO(data)) as image:
            software = str(image.getexif().get(0x0131, ""))
        report["metadata"] = {"software": software}
        if tool := editing_tool(software):
            report["signals"].append(signal("editing_software", "warning", f"Image metadata names editing software ({tool})."))
        return report
    with fitz.open(stream=data, filetype="pdf") as doc:
        meta = doc.metadata or {}
        report["metadata"] = {key: meta.get(key) or "" for key in ("producer", "creator", "creationDate", "modDate")}
        if tool := editing_tool(meta.get("producer"), meta.get("creator")):
            report["signals"].append(signal("editing_software", "warning", f"PDF metadata names editing software ({tool})."))
        created, modified = pdf_date(meta.get("creationDate")), pdf_date(meta.get("modDate"))
        if created and modified and modified - created > timedelta(minutes=5):
            report["signals"].append(signal("modified_after_creation", "warning",
                                            f"The PDF was modified on {modified:%Y-%m-%d %H:%M}, after its creation on {created:%Y-%m-%d %H:%M}."))
        # A linearised file legitimately carries two sections.
        allowed = 2 if doc.is_fast_webaccess else 1
        if doc.version_count > allowed:
            report["signals"].append(signal("incremental_update", "warning",
                                            f"The PDF was saved {doc.version_count - 1} more time(s) after creation; appended saves can carry later edits."))
        layer = "\n".join(page.get_text() for page in doc)
        found = candidates(layer)
        for key in CRITICAL_FIELDS:
            values = found.get(key, ([], False))[0]
            if len(values) > 1:
                report["signals"].append(signal(f"conflicting_values_{key}", "high",
                                                f"The document text contains {len(values)} different {key.replace('_', ' ')} values: {', '.join(map(str, values))}."))
        first = doc[0]
        if ocr and len(first.get_text().strip()) >= 25:
            try:
                visible, _ = structure(ocr_page(first), "tesseract_ocr")
            except Exception:
                report["ocr_crosscheck"] = "unavailable"
            else:
                report["ocr_crosscheck"] = "completed"
                page_values = candidates(first.get_text())
                for key in CRITICAL_FIELDS:
                    hidden = page_values.get(key, ([], False))[0]
                    agrees = any(same_reference(visible[key], h, ocr=True) for h in hidden) if key == "number" and key in visible else visible.get(key) in hidden
                    if key in visible and hidden and not agrees:
                        report["signals"].append(signal(f"text_layer_mismatch_{key}", "high",
                                                        f"The visible page reads {key.replace('_', ' ')} {visible[key]}, but the PDF text layer says {hidden[0]}. "
                                                        "OCR misreads are possible; compare the original carefully."))
    return report
