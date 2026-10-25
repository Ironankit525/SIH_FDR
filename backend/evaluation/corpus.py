"""Deterministic synthetic corpus of genuine and problem FDR submissions.

Every document is fictional. Each case carries what the institution declares, the document it uploads
and what the (simulated) bank actually holds, so detection can be measured before and after a bank check.
Genuine cases include deliberately awkward ones (scans, joint holdings, abbreviations) because a
detector that only meets tidy genuine receipts reports a flattering false-positive rate.
"""
import io
import random
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageFilter

BANKS = [("STATE BANK OF INDIA", "SBI"), ("PUNJAB NATIONAL BANK", "PNB"), ("BANK OF BARODA", "BOB"),
         ("CANARA BANK", None), ("HDFC BANK", "HDFC"), ("ICICI BANK", "ICICI")]
PLACES = ["Aravalli", "Brahmaputra", "Cauvery", "Deccan", "Godavari", "Himalayan", "Indus", "Konark", "Malwa", "Narmada",
          "Palghat", "Satpura", "Tapti", "Vindhya", "Yamuna", "Zanskar", "Chilika", "Nilgiri", "Sahyadri Ridge", "Thar"]
SUFFIXES = ["Institute of Technology", "College of Engineering", "Engineering College", "Institute of Engineering and Technology"]
THIRD_PARTIES = ["Shree Ganesh Educational Trust", "Sunrise Infra Developers Private Limited", "R K Sharma", "Om Sai Charitable Society",
                 "Vardhman Holdings LLP", "Anand Kumar Verma"]
BAD_LIENS = ["", "Nil", "Lien marked in favour of the issuing bank against overdraft", "Free of any lien"]

GENUINE_KINDS = {"genuine": 0.4, "genuine_scanned": 0.2, "genuine_joint_holding": 0.1, "genuine_bank_abbreviation": 0.15, "genuine_coverage_gap": 0.15}
PROBLEM_KINDS = {
    # kind: what it represents
    "overlay_amount": "Amount covered with a white box and retyped to meet the requirement",
    "incremental_date_edit": "Maturity date redacted and retyped in a PDF editor, saved incrementally",
    "hidden_text_layer": "Scanned receipt with an invisible text layer stating a larger amount",
    "editor_regenerated": "Receipt rebuilt in an image editor with a larger amount (editor named in metadata)",
    "clean_regenerated": "Receipt rebuilt with a larger amount, leaving no document traces",
    "fabricated": "Receipt for an instrument the bank never issued",
    "reused_receipt_rescan": "Another institution's genuine receipt, re-scanned and claimed with a new number",
    "duplicate_declared": "An instrument already pledged by another institution, declared with different formatting",
    "third_party_depositor": "Genuine instrument held by an unrelated person or company",
    "missing_lien": "Genuine instrument with no lien in favour of AICTE",
}


@dataclass
class Case:
    id: str
    kind: str
    label: int  # 1 = needs intervention, 0 = genuine and compliant
    institution: int
    declared: dict
    document: bytes
    bank_record: dict | None
    notes: str = ""
    extra: dict = field(default_factory=dict)


def indian(amount):
    whole, paise = f"{amount:.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups + [tail]) + "." + paise


def receipt_text(template, f):
    if template == 0:
        return (f"FIXED DEPOSIT ADVICE\n\nBank: {f['bank']}\nBranch: {f['branch']}\nFDR Number: {f['number']}\n"
                f"Depositor Name: {f['depositor_name']}\nAmount: INR {f['amount']:.2f}\nIssue Date: {f['issue_date']}\n"
                f"Maturity Date: {f['maturity_date']}\nRate of Interest: {f['rate']}% p.a.\n"
                + (f"Lien Marked in Favour of: {f['lien']}\n" if f['lien'] else "") + "\nThis is a computer generated advice.")
    if template == 1:
        d = lambda v: date.fromisoformat(v).strftime("%d/%m/%Y")
        return (f"{f['bank']}\nTERM DEPOSIT RECEIPT\n\nBank Name: {f['bank']}\nBranch: {f['branch']}\nFDR No.: {f['number']}\n"
                f"Name of Depositor: {f['depositor_name']}\nPrincipal Amount: Rs. {indian(f['amount'])}\n"
                f"Date of Deposit: {d(f['issue_date'])}\nDate of Maturity: {d(f['maturity_date'])}\n"
                f"Maturity Value: Rs. {indian(f['maturity_value'])}\n" + (f"Lien: {f['lien']}\n" if f['lien'] else "")
                + "\nAuthorised Signatory")
    d = lambda v: date.fromisoformat(v).strftime("%d-%m-%Y")
    return (f"DEPOSIT CONFIRMATION\n\nBank: {f['bank']}\nBranch: {f['branch']}\nInstrument No: {f['number']}\n"
            f"Depositor: {f['depositor_name']}\nDeposit Amount - INR {f['amount']:.2f}\nInterest Rate: {f['rate']}%\n"
            f"Maturity Amount: INR {f['maturity_value']:.2f}\nIssue Date: {d(f['issue_date'])}\nMaturity Date: {d(f['maturity_date'])}\n"
            + (f"Pledged to: {f['lien']}\n" if f['lien'] else "") + "\nSubject to the terms printed overleaf.")


def pdf_date(day, hour=10, minute=30):
    return f"D:{day.strftime('%Y%m%d')}{hour:02d}{minute:02d}00"


def render(text, issued, producer=None):
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(35, 35, 560, 800), color=(.15, .2, .35), width=1)
    page.insert_textbox(fitz.Rect(55, 70, 540, 780), text, fontsize=11, lineheight=1.6)
    stamp = pdf_date(issued)
    doc.set_metadata({"producer": producer or "Core Banking eReceipt 4.2", "creator": "Branch Teller Terminal", "creationDate": stamp, "modDate": stamp})
    data = doc.tobytes()
    doc.close()
    return data


def scan(data, rng):
    """Print-and-scan: rasterise, greyscale, slight blur and rotation, JPEG. No text layer survives."""
    with fitz.open(stream=data, filetype="pdf") as doc:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L").rotate(rng.uniform(-0.6, 0.6), fillcolor=255, expand=False)
    image = image.filter(ImageFilter.GaussianBlur(0.4))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80)
    out = fitz.open()
    page = out.new_page()
    page.insert_image(page.rect, stream=buffer.getvalue())
    result = out.tobytes()
    out.close()
    return result


def overlay(data, old, new):
    doc = fitz.open(stream=data, filetype="pdf")
    page = doc[0]
    hit = page.search_for(old)[0]
    page.draw_rect(hit + (-1, -1, 1, 1), color=(1, 1, 1), fill=(1, 1, 1))
    page.insert_text((hit.x0, hit.y1 - 2.6), new, fontsize=11)
    result = doc.tobytes()
    doc.close()
    return result


def incremental_edit(data, old, new, edited_on):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "receipt.pdf"
        path.write_bytes(data)
        doc = fitz.open(path)
        page = doc[0]
        hit = page.search_for(old)[0]
        page.add_redact_annot(hit, fill=(1, 1, 1))
        page.apply_redactions()
        page.insert_text((hit.x0, hit.y1 - 2.6), new, fontsize=11)
        meta = doc.metadata
        meta["modDate"] = pdf_date(edited_on, 16, 5)
        doc.set_metadata(meta)
        doc.saveIncr()
        doc.close()
        return path.read_bytes()


def hidden_layer(data, text_with_inflated, rng):
    scanned = fitz.open(stream=scan(data, rng), filetype="pdf")
    scanned[0].insert_textbox(fitz.Rect(55, 70, 540, 780), text_with_inflated, fontsize=11, lineheight=1.6, render_mode=3)
    result = scanned.tobytes()
    scanned.close()
    return result


def shown(template, key, value):
    """How a value is printed on a given template, for search-and-replace edits."""
    if key == "amount":
        return indian(value) if template == 1 else f"{value:.2f}"
    fmt = {0: "%Y-%m-%d", 1: "%d/%m/%Y", 2: "%d-%m-%Y"}[template]
    return date.fromisoformat(value).strftime(fmt)


def build(genuine=60, per_problem=6, seed=7, today=None):
    rng = random.Random(seed)
    today = today or date.today()
    institution_count = max(8, (genuine + per_problem * len(PROBLEM_KINDS)) // 4)
    names = [f"{PLACES[i % len(PLACES)]} {SUFFIXES[(i // len(PLACES)) % len(SUFFIXES)]}" for i in range(institution_count)]
    cases, serial = [], [0]

    def facts(institution, amount=None):
        serial[0] += 1
        bank, alias = rng.choice(BANKS)
        issued = today - timedelta(days=rng.randint(20, 300))
        tenure = rng.choice([365, 730, 1095, 1825])
        amount = amount or rng.choice([3500000, 3750000, 4000000, 5000000])
        rate = rng.choice([6.8, 7.1, 7.25, 7.5])
        return {"bank": bank, "alias": alias, "branch": rng.choice(["Main Branch", "University Road", "Civil Lines", "MG Road"]),
                "number": f"{bank.split()[0][:3]}{rng.randint(10, 99)}{serial[0]:05d}{rng.choice('ABCDEFGH')}",
                "depositor_name": names[institution], "amount": float(amount), "rate": rate,
                "maturity_value": round(amount * (1 + rate / 100 * tenure / 365), 2),
                "issue_date": issued.isoformat(), "maturity_date": (issued + timedelta(days=tenure)).isoformat(),
                "lien": "AICTE, New Delhi", "template": rng.randrange(3)}

    def declared(f, **overrides):
        values = {"instrument_type": "FDR", "bank": f["bank"], "branch": f["branch"], "number": f["number"], "depositor_name": f["depositor_name"],
                  "amount": f["amount"], "issue_date": f["issue_date"], "maturity_date": f["maturity_date"], "lien_details": f["lien"],
                  "regulatory_end_date": (date.fromisoformat(f["maturity_date"]) - timedelta(days=rng.randint(30, 200))).isoformat()}
        return {**values, **overrides}

    def bank_record(f):
        return {key: f[key] for key in ("bank", "number", "depositor_name", "issue_date", "maturity_date")} | {"amount": f["amount"]}

    def add(kind, label, institution, f, document, record, **extra):
        cases.append(Case(f"{'G' if not label else 'P'}-{len(cases) + 1:03d}", kind, label, institution, extra.pop("declared", None) or declared(f),
                          document, record, extra.pop("notes", ""), extra))

    # Most institutions are honest; problems cluster in a minority, with occasional first offences elsewhere.
    order = rng.sample(range(institution_count), institution_count)
    risky, honest = order[:max(2, institution_count * 3 // 10)], order[max(2, institution_count * 3 // 10):]

    def pick(problem):
        return rng.choice((risky if rng.random() < 0.8 else honest) if problem else (honest if rng.random() < 0.85 else risky))
    kinds = list(GENUINE_KINDS)
    weights = list(GENUINE_KINDS.values())
    for _ in range(genuine):
        kind = rng.choices(kinds, weights)[0]
        inst = pick(False)
        f = facts(inst)
        overrides = {}
        if kind == "genuine_joint_holding":
            f["depositor_name"] = f"Member Secretary AICTE and {names[inst]}"
        if kind == "genuine_bank_abbreviation":
            f["bank"], f["alias"] = next((b, a) for b, a in rng.sample(BANKS, len(BANKS)) if a)
            overrides["bank"] = f["alias"]
        if kind == "genuine_coverage_gap":
            # Short FDR for a longer obligation: legitimate now, renewal needed before maturity.
            f["maturity_date"] = (today + timedelta(days=rng.randint(20, 150))).isoformat()
            # A genuine receipt prints the maturity value for its own term.
            term = (date.fromisoformat(f["maturity_date"]) - date.fromisoformat(f["issue_date"])).days
            f["maturity_value"] = round(f["amount"] * (1 + f["rate"] / 100 * term / 365), 2)
            overrides["regulatory_end_date"] = (today + timedelta(days=700)).isoformat()
        text = receipt_text(f["template"], f)
        document = render(text, date.fromisoformat(f["issue_date"]))
        if kind == "genuine_scanned":
            document = scan(document, rng)
        add(kind, 0, inst, f, document, bank_record(f), declared=declared(f, **overrides))
    genuine_cases = [c for c in cases]

    for kind in PROBLEM_KINDS:
        for _ in range(per_problem):
            inst = pick(True)
            if kind in ("overlay_amount", "incremental_date_edit", "hidden_text_layer", "editor_regenerated", "clean_regenerated"):
                true = facts(inst, amount=rng.choice([1500000, 2000000, 2500000]))
                forged = dict(true)
                if kind == "incremental_date_edit":
                    true["amount"] = forged["amount"] = 3500000.0
                    forged["maturity_date"] = (date.fromisoformat(true["maturity_date"]) + timedelta(days=730)).isoformat()
                else:
                    forged["amount"] = 3500000.0
                original = render(receipt_text(true["template"], true), date.fromisoformat(true["issue_date"]))
                t = true["template"]
                if kind == "overlay_amount":
                    document = overlay(original, shown(t, "amount", true["amount"]), shown(t, "amount", forged["amount"]))
                elif kind == "incremental_date_edit":
                    document = incremental_edit(original, shown(t, "maturity_date", true["maturity_date"]),
                                                shown(t, "maturity_date", forged["maturity_date"]), today - timedelta(days=3))
                elif kind == "hidden_text_layer":
                    document = hidden_layer(original, receipt_text(t, forged), rng)
                else:
                    document = render(receipt_text(t, forged), date.fromisoformat(true["issue_date"]),
                                      producer="Adobe Photoshop 25.1 (Windows)" if kind == "editor_regenerated" else None)
                add(kind, 1, inst, forged, document, bank_record(true))
            elif kind == "fabricated":
                f = facts(inst)
                add(kind, 1, inst, f, render(receipt_text(f["template"], f), date.fromisoformat(f["issue_date"])), None)
            elif kind == "reused_receipt_rescan":
                source = rng.choice(genuine_cases)
                rescanned = scan(source.document, rng) if source.kind != "genuine_scanned" else source.document
                number = source.declared["number"][:-1] + ("Z" if source.declared["number"][-1] != "Z" else "Y")
                own = facts(inst)
                claim = {**source.declared, "number": number, "depositor_name": names[inst], "lien_details": "AICTE, New Delhi"}
                add(kind, 1, inst, own, rescanned, None, declared=claim, notes=f"Receipt of {source.id}")
            elif kind == "duplicate_declared":
                source = rng.choice(genuine_cases)
                number = source.declared["number"]
                variant = f"{number[:3]}-{number[3:]}" if rng.random() < 0.5 else number.lower()
                bank = next((a for b, a in BANKS if b == source.declared["bank"] and a), source.declared["bank"].title())
                own = facts(inst)
                claim = {**source.declared, "number": variant, "bank": bank, "depositor_name": names[inst]}
                add(kind, 1, inst, own, source.document, None, declared=claim, notes=f"Instrument of {source.id}")
            elif kind == "third_party_depositor":
                f = facts(inst)
                f["depositor_name"] = rng.choice(THIRD_PARTIES)
                add(kind, 1, inst, f, render(receipt_text(f["template"], f), date.fromisoformat(f["issue_date"])), bank_record(f))
            elif kind == "missing_lien":
                f = facts(inst)
                f["lien"] = rng.choice(BAD_LIENS)
                add(kind, 1, inst, f, render(receipt_text(f["template"], f), date.fromisoformat(f["issue_date"])), bank_record(f))
    return names, cases
