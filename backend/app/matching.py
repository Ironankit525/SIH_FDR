"""Normalisation used to compare names and references that people type differently."""
import hashlib
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

BANK_ALIASES = {
    "SBI": "STATE BANK OF INDIA", "PNB": "PUNJAB NATIONAL BANK", "BOB": "BANK OF BARODA", "BOI": "BANK OF INDIA",
    "UBI": "UNION BANK OF INDIA", "CBI": "CENTRAL BANK OF INDIA", "IOB": "INDIAN OVERSEAS BANK", "UCO": "UCO BANK",
    "BOM": "BANK OF MAHARASHTRA", "PSB": "PUNJAB AND SIND BANK", "HDFC": "HDFC BANK", "ICICI": "ICICI BANK",
    "AXIS": "AXIS BANK", "KOTAK": "KOTAK MAHINDRA BANK", "IDBI": "IDBI BANK", "YES": "YES BANK",
}
BANK_STOPWORDS = {"THE", "LTD", "LIMITED", "OF", "AND", "BANK", "CO", "CORPORATION"}
NAME_STOPWORDS = {"THE", "OF", "AND", "M", "S", "MS", "FOR", "IN", "A", "AN"}
AICTE = re.compile(r"\bAICTE\b|ALL\s+INDIA\s+COUNCIL\s+FOR\s+TECHNICAL\s+EDUCATION", re.I)
# Joint holdings name AICTE alongside the institution; these words say nothing about the institution itself.
JOINT_HOLDING_WORDS = {"AICTE", "ALL", "INDIA", "COUNCIL", "TECHNICAL", "EDUCATION", "MEMBER", "SECRETARY", "JOINTLY", "WITH"}


def normalise_number(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def normalise_bank(value):
    words = re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper()).split()
    compact = "".join(words)
    if compact in BANK_ALIASES:
        words = BANK_ALIASES[compact].split()
    return "".join(w for w in words if w not in BANK_STOPWORDS) or compact


def name_tokens(value):
    return [w for w in re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper()).split() if w not in NAME_STOPWORDS]


def names_match(depositor, institution):
    """True when the depositor is the institution, allowing joint holdings with AICTE."""
    holder = [w for w in name_tokens(depositor) if w not in JOINT_HOLDING_WORDS]
    owner = name_tokens(institution)
    if not holder or not owner:
        return False
    if set(owner) <= set(holder):
        return True
    return SequenceMatcher(None, " ".join(holder), " ".join(owner)).ratio() >= 0.88


# Characters OCR commonly confuses in printed references.
OCR_LOOKALIKES = str.maketrans("OQDILSBZG", "001115826")


def same_reference(a, b, ocr=False):
    a, b = normalise_number(a), normalise_number(b)
    return a == b or (ocr and a.translate(OCR_LOOKALIKES) == b.translate(OCR_LOOKALIKES))


def same_bank(a, b):
    return normalise_bank(a) == normalise_bank(b)


def same_name(a, b):
    return name_tokens(a) == name_tokens(b)


def mentions_aicte(value):
    return bool(AICTE.search(str(value or "")))


def same_amount(a, b):
    try:
        return Decimal(str(a).replace(",", "")) == Decimal(str(b).replace(",", ""))
    except (InvalidOperation, ValueError):
        return False


def same_text(a, b):
    return " ".join(str(a or "").split()).casefold() == " ".join(str(b or "").split()).casefold()


def text_fingerprint(text):
    compact = re.sub(r"[^A-Z0-9]", "", str(text or "").upper())
    return hashlib.sha256(compact.encode()).hexdigest() if len(compact) >= 40 else None
