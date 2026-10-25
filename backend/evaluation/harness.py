"""Runs the corpus through the real API (create → upload → submit → officer bank check) and measures the risk engine."""
from collections import defaultdict


from app import risk, security
from app.models import Institution, MockBankRecord, Programme, User
from app.security import passwords

from .corpus import GENUINE_KINDS, PROBLEM_KINDS

PASSWORD = "EvaluationOnly2026!"
STAGES = ("intake", "after_bank_check")


def setup(factory, names, cases):
    with factory() as db:
        password_hash = passwords.hash(PASSWORD)
        accounts = {}
        for index, name in enumerate(names):
            institution = Institution(code=f"EVAL-{index:03d}", name=name, state="Evaluation", contact_email=f"eval{index}@eval.local")
            db.add(institution)
            db.flush()
            programme = Programme(institution_id=institution.id, name="Engineering and Technology", level="undergraduate")
            db.add(programme)
            db.add(User(email=f"eval{index}@eval.local", name=f"Evaluation user {index}", role="institution",
                        institution_id=institution.id, password_hash=password_hash))
            db.flush()
            accounts[index] = programme.id
        numbers = set()
        for case in cases:
            if case.bank_record and case.bank_record["number"] not in numbers:
                numbers.add(case.bank_record["number"])
                db.add(MockBankRecord(number=case.bank_record["number"], fields=case.bank_record, available=True))
        db.commit()
    return accounts


def login(client, email, password):
    security._attempts.clear()  # the harness signs in many institutions from one address
    c = client(None)
    result = c.post("/api/auth/login", json={"email": email, "password": password})
    assert result.status_code == 200, result.text
    c.headers["X-CSRF-Token"] = c.cookies.get("df_csrf")
    return c


def snapshot(officer, deposit_id):
    data = officer.get(f"/api/deposits/{deposit_id}/risk").json()
    return {"score": float(data["score"]), "level": data["level"], "signals": sorted({s["key"] for s in data["signals"]})}


def run(factory, client, names, cases, officer_password):
    programmes = setup(factory, names, cases)
    officer = login(client, "officer@demo.local", officer_password)
    sessions, results = {}, []
    for case in cases:
        if case.institution not in sessions:
            sessions[case.institution] = login(client, f"eval{case.institution}@eval.local", PASSWORD)
        c = sessions[case.institution]
        security._attempts.clear()  # many submissions per institution in a few seconds
        created = c.post("/api/deposits", json={**case.declared, "programme_id": programmes[case.institution]})
        row = {"id": case.id, "kind": case.kind, "label": case.label, "notes": case.notes}
        if created.status_code == 409:
            # Refused at submission as a duplicate: the strongest possible outcome.
            row.update(blocked=True, stages={stage: {"score": 100.0, "level": "blocked", "signals": ["duplicate_blocked"]} for stage in STAGES})
            results.append(row)
            continue
        assert created.status_code == 201, (case.id, created.text)
        deposit_id = created.json()["id"]
        upload = c.post(f"/api/deposits/{deposit_id}/documents", files={"file": ("receipt.pdf", case.document, "application/pdf")})
        assert upload.status_code == 201, (case.id, upload.text)
        assert c.post(f"/api/deposits/{deposit_id}/submit").status_code == 200, case.id
        row.update(deposit_id=deposit_id, blocked=False, stages={"intake": snapshot(officer, deposit_id)})
        results.append(row)
    for row in results:
        if row["blocked"]:
            continue
        security._attempts.clear()  # one officer makes two writes per case, beyond the per-minute write limit
        for step in ("assign", "verification/mock"):
            response = officer.post(f"/api/deposits/{row['deposit_id']}/{step}")
            assert response.status_code == 200, (row["id"], step, response.status_code, response.text)
    # Rescore everything once all cases exist, as the daily sweep would, so institution history is complete.
    security._attempts.clear()
    admin = login(client, "admin@demo.local", officer_password)
    admin.post("/api/admin/monitor/run")
    for row in results:
        if not row["blocked"]:
            row["stages"]["after_bank_check"] = snapshot(officer, row["deposit_id"])
    return results


def auc(positives, negatives):
    """Probability that a random problem case outscores a random genuine one (ties count half)."""
    if not positives or not negatives:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return round(wins / (len(positives) * len(negatives)), 3)


def rate(numerator, denominator):
    return round(numerator / denominator, 3) if denominator else None


def metrics(results, thresholds=None):
    thresholds = thresholds or risk.DEFAULT_THRESHOLDS
    out = {"cases": len(results), "problem_cases": sum(r["label"] for r in results), "genuine_cases": sum(1 - r["label"] for r in results),
           "thresholds": thresholds, "stages": {}}
    for stage in STAGES:
        scored = [(r, r["stages"][stage]) for r in results]
        pos = [s["score"] for r, s in scored if r["label"]]
        neg = [s["score"] for r, s in scored if not r["label"]]
        ranked = sorted(scored, key=lambda item: -item[1]["score"])
        top = ranked[:10]
        per_kind = {}
        for kind in list(GENUINE_KINDS) + list(PROBLEM_KINDS):
            group = [s["score"] for r, s in scored if r["kind"] == kind]
            if group:
                per_kind[kind] = {"cases": len(group), "at_least_medium": rate(sum(x >= thresholds["medium"] for x in group), len(group)),
                                  "at_least_high": rate(sum(x >= thresholds["high"] for x in group), len(group)),
                                  "median_score": sorted(group)[len(group) // 2]}
        detectors = defaultdict(lambda: [0, 0])
        for r, s in scored:
            for key in s["signals"]:
                detectors[key][1 - r["label"]] += 1
        out["stages"][stage] = {
            "auc": auc(pos, neg),
            "recall_at_medium": rate(sum(x >= thresholds["medium"] for x in pos), len(pos)),
            "recall_at_high": rate(sum(x >= thresholds["high"] for x in pos), len(pos)),
            "false_positive_rate_at_medium": rate(sum(x >= thresholds["medium"] for x in neg), len(neg)),
            "false_positive_rate_at_high": rate(sum(x >= thresholds["high"] for x in neg), len(neg)),
            "precision_at_10": rate(sum(r["label"] for r, _ in top), len(top)),
            "per_kind": per_kind,
            "detectors": {key: {"problem_cases": p, "genuine_cases": g, "precision": rate(p, p + g)}
                          for key, (p, g) in sorted(detectors.items(), key=lambda item: -sum(item[1]))},
        }
    return out
