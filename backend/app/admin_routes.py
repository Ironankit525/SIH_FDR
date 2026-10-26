import io
import csv
import json
from pathlib import Path
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, func, text
from . import schemas
from .audit import audit, event_digest
from .config import settings
from .db import get_db
from .models import (User, Role, Institution, SecurityDeposit, Instrument, RuleVersion, RegulatoryRule, RuleApproval,
                     Notification, NotificationRead, AuditLog, AuditChainHead, Configuration, Document, VerificationRequest, VerificationEvidence, ReleaseRequest, RiskWeightVersion)
from .security import current_user, require_roles, passwords
from .presenters import record, deposit_summary, audit_record
from . import importer, reports, risk
from .workflows import configuration, DEFAULT_WORKFLOW, DEFAULT_ALERTS, monitor

router = APIRouter(prefix="/api", tags=["Dashboards and administration"])


def scoped_deposits(db, user):
    query = select(SecurityDeposit).order_by(SecurityDeposit.created_at.desc())
    if user.role == "institution":
        query = query.where(SecurityDeposit.institution_id == user.institution_id)
    return db.scalars(query).all()


@router.get("/dashboard")
def dashboard(user=Depends(current_user), db=Depends(get_db)):
    deposits = scoped_deposits(db, user)
    rows = [deposit_summary(db, d, user) for d in deposits]
    total = sum(float(r["instrument"]["amount"]) for r in rows)
    counts = Counter(r["status"] for r in rows)
    maturity = Counter("Overdue" if r["days_to_maturity"] < 0 else "0–30 days" if r["days_to_maturity"] <= 30 else "31–90 days" if r["days_to_maturity"] <= 90 else "90+ days" for r in rows if r["status"] != "released")
    months = Counter(d.created_at.strftime("%Y-%m") for d in deposits)
    turnarounds = []
    for d in deposits:
        if not d.submitted_at:
            continue
        evidence = db.scalar(select(VerificationEvidence).join(VerificationRequest).where(VerificationRequest.deposit_id == d.id).order_by(VerificationEvidence.created_at).limit(1))
        if evidence:
            turnarounds.append({"reference": d.reference, "hours": round(max(0, (evidence.created_at.replace(tzinfo=None) - d.submitted_at.replace(tzinfo=None)).total_seconds() / 3600), 2)})
    deposit_ids = [d.id for d in deposits]
    pending_releases = db.scalar(select(func.count()).select_from(ReleaseRequest).where(ReleaseRequest.deposit_id.in_(deposit_ids), ReleaseRequest.status.in_(["under_review", "returned"])))
    result = {"total_records": len(rows), "total_value": total, "pending_verification": sum(r["instrument"]["verification_status"] in ("pending", "mock_pending", "inconclusive", "mock_inconclusive") for r in rows),
            "officially_confirmed": sum(r["instrument"]["verification_status"] == "officially_confirmed" for r in rows),
            "mock_confirmed": sum(r["instrument"]["verification_status"] == "mock_confirmed" for r in rows),
            "discrepancies": sum(r["open_discrepancies"] for r in rows), "expiring": sum(0 <= r["days_to_maturity"] <= 90 for r in rows),
            "overdue": maturity["Overdue"], "pending_release": pending_releases, "completed_approvals": counts["released"] + counts["release_authorised"],
            "renewal_cases": sum(len(db.scalars(select(Instrument.id).where(Instrument.deposit_id == d.id)).all()) > 1 for d in deposits),
            "status_distribution": [{"name": key.replace("_", " "), "value": value} for key, value in counts.items()],
            "maturity_distribution": [{"name": name, "value": maturity[name]} for name in ["Overdue", "0–30 days", "31–90 days", "90+ days"]],
            "monthly_submissions": [{"name": key, "value": value} for key, value in sorted(months.items())],
            "verification_turnaround": turnarounds, "recent": rows[:6], "fictional_data": True}
    if user.role != "institution":
        active = [r for r in rows if r["risk"] and r["status"] != "released"]
        levels = Counter(r["risk"]["level"] for r in active)
        result["risk_distribution"] = [{"name": level, "value": levels[level]} for level in ("none", "low", "medium", "high", "critical")]
        institutions = {}
        for r in active:
            entry = institutions.setdefault(r["institution_id"], {"institution": r["institution_name"], "cases": 0, "elevated": 0, "highest": 0.0, "highest_level": "low", "highest_reference": ""})
            entry["cases"] += 1
            entry["elevated"] += r["risk"]["level"] in ("high", "critical")
            if r["risk"]["score"] > entry["highest"]:
                entry["highest"], entry["highest_level"], entry["highest_reference"] = r["risk"]["score"], r["risk"]["level"], r["reference"]
        result["risk_institutions"] = sorted(institutions.values(), key=lambda e: (-e["elevated"], -e["highest"]))[:5]
    return result


EVALUATION = Path(__file__).resolve().parents[1] / "evaluation" / "latest.json"


@router.get("/risk/evaluation")
def risk_evaluation(user=Depends(current_user)):
    """Headline results of the latest synthetic-corpus evaluation (python -m evaluation)."""
    require_roles(user, "verification", "clearance", "authority", "admin", "auditor")
    if not EVALUATION.exists():
        raise HTTPException(404, "No evaluation has been run")
    data = json.loads(EVALUATION.read_text())
    metrics = data["metrics"]
    return {"generated_on": data["generated_on"], "engine_version": risk.ENGINE_VERSION, "cases": metrics["cases"],
            "problem_cases": metrics["problem_cases"], "genuine_cases": metrics["genuine_cases"],
            "stages": {stage: {key: values[key] for key in ("auc", "recall_at_medium", "recall_at_high", "false_positive_rate_at_medium", "precision_at_10")}
                       for stage, values in metrics["stages"].items()},
            "notice": "Measured on a fictional synthetic corpus written by the same team as the detectors. Not real-world fraud detection accuracy."}


@router.get("/risk/evaluation/details")
def risk_evaluation_details(user=Depends(current_user)):
    """Results by kind of case, signal precision, and every miss and false alarm from the latest evaluation."""
    require_roles(user, "verification", "clearance", "authority", "admin", "auditor")
    if not EVALUATION.exists():
        raise HTTPException(404, "No evaluation has been run")
    from evaluation.corpus import COMPLIANCE_KINDS, GENUINE_KINDS, PROBLEM_KINDS
    from evaluation.report import GENUINE_NOTES
    data = json.loads(EVALUATION.read_text())
    metrics = data["metrics"]
    medium = metrics["thresholds"]["medium"]
    after = lambda c: c["stages"]["after_bank_check"]
    return {"generated_on": data["generated_on"], "engine_version": risk.ENGINE_VERSION, "corpus": data["corpus"], "metrics": metrics,
            "kinds": {**{k: {"problem": True, "compliance": k in COMPLIANCE_KINDS, "description": v} for k, v in PROBLEM_KINDS.items()},
                      **{k: {"problem": False, "description": GENUINE_NOTES[k]} for k in GENUINE_KINDS}},
            "misses": [{"id": c["id"], "kind": c["kind"], **after(c)} for c in data["cases"] if c["label"] and c["kind"] not in COMPLIANCE_KINDS and after(c)["score"] < medium],
            "false_alarms": [{"id": c["id"], "kind": c["kind"], **after(c)} for c in data["cases"] if not c["label"] and after(c)["score"] >= medium],
            "notice": "Measured on a fictional synthetic corpus written by the same team as the detectors. Not real-world fraud detection accuracy."}


@router.get("/notifications")
def notifications(user=Depends(current_user), db=Depends(get_db)):
    query = select(Notification).order_by(Notification.created_at.desc())
    if user.role == "institution":
        query = query.where(Notification.institution_id == user.institution_id)
    return [{**record(n), "read": db.get(NotificationRead, (n.id, user.id)) is not None} for n in db.scalars(query).all()]


@router.post("/notifications/read-all")
def read_all_notifications(user=Depends(current_user), db=Depends(get_db)):
    query = select(Notification.id)
    if user.role == "institution":
        query = query.where(Notification.institution_id == user.institution_id)
    read = set(db.scalars(select(NotificationRead.notification_id).where(NotificationRead.user_id == user.id)).all())
    unread = [n for n in db.scalars(query).all() if n not in read]
    db.add_all(NotificationRead(notification_id=n, user_id=user.id) for n in unread)
    db.commit()
    return {"marked": len(unread)}


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: str, user=Depends(current_user), db=Depends(get_db)):
    item = db.get(Notification, notification_id)
    if not item or (user.role == "institution" and item.institution_id != user.institution_id):
        raise HTTPException(404, "Notification not found")
    if not db.get(NotificationRead, (item.id, user.id)):
        db.add(NotificationRead(notification_id=item.id, user_id=user.id))
        db.commit()
    return {"message": "Marked as read"}


@router.get("/audit")
def audit_logs(action: str = "", actor: str = "", entity: str = "", date_from: date | None = None, date_to: date | None = None,
               limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin", "auditor", "authority", "verification", "clearance")
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if actor.strip().lower() == "system":
        query = query.where(AuditLog.actor_id.is_(None))
    elif actor:
        term = f"%{actor.strip().lower()}%"
        query = query.where(AuditLog.actor_id.in_(select(User.id).where(func.lower(User.name).like(term) | func.lower(User.email).like(term))))
    if entity:
        # A deposit reference finds that case's events; anything else matches the start of a record id.
        deposit_id = db.scalar(select(SecurityDeposit.id).where(SecurityDeposit.reference == entity.strip().upper()))
        query = query.where(AuditLog.entity_id == deposit_id) if deposit_id else query.where(AuditLog.entity_id.startswith(entity.strip()))
    if date_from:
        query = query.where(AuditLog.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        query = query.where(AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [audit_record(db, a) for a in items], "total": total, "limit": limit, "offset": offset,
            "actions": db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)).all()}


def safe_csv(value):
    value = str(value if value is not None else "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


@router.get("/reports/export")
def export_report(kind: str = "deposits", user=Depends(current_user), db=Depends(get_db)):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if kind in reports.REPORTS:
        build, roles = reports.REPORTS[kind]
        if roles:
            require_roles(user, *roles)
        header, rows = build(db, scoped_deposits(db, user))
        writer.writerow(header)
        writer.writerows([safe_csv(v) for v in row] for row in rows)
    elif kind == "audit":
        require_roles(user, "auditor", "admin", "authority")
        writer.writerow(["Time", "Actor", "Action", "Record", "Event hash"])
        for item in db.scalars(select(AuditLog).order_by(AuditLog.created_at)).all():
            writer.writerow([safe_csv(v) for v in (item.created_at, item.actor_id, item.action, item.entity_id, item.event_hash)])
    elif kind == "deposits":
        officials = user.role != "institution"
        writer.writerow(["Reference", "Institution", "Programme", "Bank", "Instrument", "Amount INR", "Maturity", "Status", "Verification"]
                        + (["Risk score", "Risk level"] if officials else []) + ["Data"])
        for d in scoped_deposits(db, user):
            r = deposit_summary(db, d, user)
            risk_columns = [r["risk"]["score"], r["risk"]["level"]] if officials and r["risk"] else ["", ""] if officials else []
            writer.writerow([safe_csv(v) for v in (r["reference"], r["institution_name"], r["programme"], r["instrument"]["bank"], r["instrument"]["number"], r["instrument"]["amount"], r["instrument"]["maturity_date"], r["status"], r["instrument"]["verification_status"], *risk_columns, "FICTIONAL DEMO")])
    else:
        raise HTTPException(422, "Unsupported report type")
    audit(db, user, "report_exported", user.id, user.institution_id, after={"kind": kind})
    db.commit()
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="depositflow-{kind}.csv"'})


@router.get("/rules")
def rules(user=Depends(current_user), db=Depends(get_db)):
    return [{**record(v), "title": db.get(RegulatoryRule, v.rule_id).title} for v in db.scalars(select(RuleVersion).order_by(RuleVersion.created_at.desc())).all()]


@router.post("/admin/rules", status_code=201)
def propose_rule(body: schemas.RuleInput, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    rule = db.get(RegulatoryRule, body.rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    version_number = (db.scalar(select(func.max(RuleVersion.version)).where(RuleVersion.rule_id == rule.id)) or 0) + 1
    item = RuleVersion(**body.model_dump(), version=version_number, proposed_by=user.id)
    db.add(item)
    audit(db, user, "rule_change_proposed", rule.id, after={"version": version_number, "config": body.config.model_dump()})
    db.commit()
    return record(item)


@router.post("/admin/rules/{version_id}/approve")
def approve_rule(version_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    item = db.scalar(select(RuleVersion).where(RuleVersion.id == version_id).with_for_update())
    if not item:
        raise HTTPException(404, "Rule version not found")
    if item.proposed_by == user.id:
        raise HTTPException(403, "A different administrator must approve the proposed rule")
    if item.status != "proposed":
        raise HTTPException(409, "Only proposed rule versions can be approved")
    # Keep approved historical versions queryable for their effective periods.
    # The calculator selects the latest effective-from date, then version number.
    item.status = "active"
    db.add(RuleApproval(version_id=item.id, approved_by=user.id, notes=body.notes))
    audit(db, user, "rule_change_approved", item.rule_id, after={"version": item.version, "notes": body.notes})
    db.commit()
    return record(item)


@router.get("/admin/risk-weights")
def risk_weights(user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin", "auditor")
    versions = db.scalars(select(RiskWeightVersion).order_by(RiskWeightVersion.version.desc())).all()
    return {"active": risk.active_policy(db), "engine_version": risk.ENGINE_VERSION,
            "signals": {key: {"category": c, "default_weight": w, "strength": s} for key, (c, w, s) in risk.SIGNALS.items()},
            "versions": [{**record(v), "proposed_by_name": user_name(db, v.proposed_by), "approved_by_name": user_name(db, v.approved_by)} for v in versions]}


def user_name(db, user_id):
    person = db.get(User, user_id) if user_id else None
    return person.name if person else None


@router.post("/admin/risk-weights/preview")
def preview_risk_weights(body: schemas.RiskPolicyInput, user=Depends(current_user), db=Depends(get_db)):
    """What a policy would do to every open case, computed without storing anything."""
    require_roles(user, "admin", "auditor")
    weights = {key: weight for key, (_, weight, _) in risk.SIGNALS.items()}
    policy = {"version": "preview", "weights": {**weights, **body.weights}, "thresholds": body.thresholds,
              "category_caps": dict(risk.DEFAULT_CAPS) if body.category_caps is None else body.category_caps}
    levels = ("none", "low", "medium", "high", "critical")
    current, proposed, changes = dict.fromkeys(levels, 0), dict.fromkeys(levels, 0), []
    for deposit in db.scalars(select(SecurityDeposit).where(SecurityDeposit.status != "released")).all():
        before, after = risk.latest(db, deposit.id), risk.evaluate(db, deposit, policy)
        if not before:
            continue
        current[before.level] += 1
        proposed[after["level"]] += 1
        if after["level"] != before.level:
            changes.append({"deposit_id": deposit.id, "reference": deposit.reference, "institution": db.get(Institution, deposit.institution_id).name,
                            "from_score": float(before.score), "from_level": before.level, "to_score": after["score"], "to_level": after["level"]})
    changes.sort(key=lambda c: -abs(c["to_score"] - c["from_score"]))
    return {"cases": sum(current.values()), "current": current, "proposed": proposed, "changes": changes[:25], "changed": len(changes)}


@router.post("/admin/risk-weights", status_code=201)
def propose_risk_weights(body: schemas.RiskWeightsInput, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    number = (db.scalar(select(func.max(RiskWeightVersion.version))) or 0) + 1
    item = RiskWeightVersion(version=number, weights=body.weights, category_caps=dict(risk.DEFAULT_CAPS) if body.category_caps is None else body.category_caps,
                             thresholds=body.thresholds, notes=body.notes, proposed_by=user.id)
    db.add(item)
    audit(db, user, "risk_weights_proposed", "risk-weights", after={"version": number, **body.model_dump()})
    db.commit()
    return record(item)


@router.post("/admin/risk-weights/{version_id}/approve")
def approve_risk_weights(version_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    item = db.scalar(select(RiskWeightVersion).where(RiskWeightVersion.id == version_id).with_for_update())
    if not item:
        raise HTTPException(404, "Risk weight version not found")
    if item.proposed_by == user.id:
        raise HTTPException(403, "A different administrator must approve the proposed risk weights")
    if item.status != "proposed":
        raise HTTPException(409, "Only proposed versions can be approved")
    for previous in db.scalars(select(RiskWeightVersion).where(RiskWeightVersion.status == "active")).all():
        previous.status = "superseded"
    item.status, item.approved_by = "active", user.id
    audit(db, user, "risk_weights_approved", "risk-weights", after={"version": item.version, "notes": body.notes})
    db.flush()
    # Every case is rescored under the new policy, so scores in one queue are comparable.
    policy = risk.active_policy(db)
    for deposit in db.scalars(select(SecurityDeposit)).all():
        risk.assess(db, deposit, policy)
    db.commit()
    return record(item)


@router.post("/admin/import")
async def import_deposits(file: UploadFile = File(...), commit: bool = Form(False), user=Depends(current_user), db=Depends(get_db)):
    """Check (default) or import existing deposit records from CSV. Only rows without problems are imported."""
    require_roles(user, "admin")
    rows = importer.read_rows(await file.read(importer.MAX_BYTES + 1))
    result = importer.run(db, user, rows, (file.filename or "import.csv")[:120], commit)
    if commit:
        audit(db, user, "deposits_import_completed", user.id, after={"file": file.filename, "imported": result["ready"], "rejected": result["errors"]})
        db.commit()
    else:
        db.rollback()
    return result


@router.get("/admin/users")
def users(user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    return [record(u) for u in db.scalars(select(User).order_by(User.name)).all()]


@router.post("/admin/users", status_code=201)
def create_user(body: schemas.UserInput, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    if body.role == "institution" and not db.get(Institution, body.institution_id or "00000000-0000-0000-0000-000000000000"):
        raise HTTPException(422, "Institution accounts need an existing institution")
    if body.role == "clearance" and not body.clearance_cell:
        raise HTTPException(422, "Clearance officers need an assigned cell")
    item = User(**body.model_dump(exclude={"password"}), password_hash=passwords.hash(body.password))
    item.email = item.email.lower()
    db.add(item)
    db.flush()
    audit(db, user, "user_created", item.id, after={"email": item.email, "role": item.role})
    db.commit()
    return record(item)


@router.post("/admin/users/{user_id}/toggle")
def toggle_user(user_id: str, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == user.id:
        raise HTTPException(409, "You cannot disable your own account")
    target.active = not target.active
    audit(db, user, "user_access_changed", target.id, after={"active": target.active})
    db.commit()
    return record(target)


@router.get("/admin/config")
def get_config(user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    return {"workflow": configuration(db, "workflow", DEFAULT_WORKFLOW), "alerts": configuration(db, "alerts", DEFAULT_ALERTS)}


def save_config(db, user, key, value):
    current = db.get(Configuration, key)
    before = current.value if current else {}
    if current:
        current.value = value
    else:
        db.add(Configuration(key=key, value=value))
    audit(db, user, "configuration_updated", "config:" + key, before=before, after=value)
    db.commit()
    return value


@router.put("/admin/config/workflow")
def workflow_config(body: schemas.WorkflowInput, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    if settings.environment == "production" and body.allow_mock_for_demo:
        raise HTTPException(422, "Production workflows cannot accept simulated verification")
    return save_config(db, user, "workflow", body.model_dump())


@router.put("/admin/config/alerts")
def alert_config(body: schemas.AlertInput, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    return save_config(db, user, "alerts", body.model_dump())


@router.post("/admin/monitor/run")
def run_monitor(user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin", "verification")
    created = monitor(db, force_detection=True)
    audit(db, user, "deadline_monitor_run", user.id, after={"notifications_created": created})
    db.commit()
    return {"notifications_created": created}


@router.get("/admin/monitor")
def system_monitor(user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "admin")
    db.execute(text("SELECT 1"))
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id)).all()
    heads, intact = {}, True
    for event in logs:
        if event.previous_hash != heads.get(event.entity_id, "") or event.event_hash != event_digest(event):
            intact = False
        heads[event.entity_id] = event.event_hash
    recorded_heads = {head.entity_id: head.event_hash for head in db.scalars(select(AuditChainHead)).all()}
    intact = intact and heads == recorded_heads
    import shutil
    return {"database": "connected", "database_engine": "SQLite (lightweight)" if settings.database_url.startswith("sqlite") else "PostgreSQL",
            "storage": "encrypted private local files" if settings.storage_backend == "local" else "encrypted private S3 objects",
            "jobs": settings.job_mode, "ocr_available": shutil.which("tesseract") is not None,
            "extraction_provider": settings.extraction_provider,
            "malware_scanning": "required" if settings.require_malware_scan else "structure validation only; ClamAV optional in local demo",
            "audit_chain_intact": intact, "audit_events": len(logs),
            "queued_documents": db.scalar(select(func.count()).select_from(Document).where(Document.processing_status == "queued")),
            "processing_documents": db.scalar(select(func.count()).select_from(Document).where(Document.processing_status == "processing")),
            "failed_documents": db.scalar(select(func.count()).select_from(Document).where(Document.processing_status == "failed"))}
