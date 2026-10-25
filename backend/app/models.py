"""Normalised persistence shared by PostgreSQL and the lightweight SQLite demo."""
from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Identity:
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Role(Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    permissions: Mapped[list] = mapped_column(JSON)


class Institution(Identity, Base):
    __tablename__ = "institutions"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(80))
    ownership: Mapped[str] = mapped_column(String(40), default="private")
    land_arrangement: Mapped[str] = mapped_column(String(40), default="owned")
    approval_year: Mapped[int] = mapped_column(Integer, default=2026)
    contact_email: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(Text, default="")
    fictional: Mapped[bool] = mapped_column(Boolean, default=True)


class Programme(Identity, Base):
    __tablename__ = "institution_programmes"
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(30), default="undergraduate")
    __table_args__ = (UniqueConstraint("institution_id", "name", "level"),)


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(ForeignKey("roles.name"))
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id"), nullable=True, index=True)
    clearance_cell: Mapped[str | None] = mapped_column(String(60), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuthSession(Identity, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegulatoryRule(Identity, Base):
    __tablename__ = "regulatory_rules"
    code: Mapped[str] = mapped_column(String(60), unique=True)
    title: Mapped[str] = mapped_column(String(200))


class RuleVersion(Identity, Base):
    __tablename__ = "rule_versions"
    rule_id: Mapped[str] = mapped_column(ForeignKey("regulatory_rules.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date] = mapped_column(Date)
    config: Mapped[dict] = mapped_column(JSON)
    source_reference: Mapped[str] = mapped_column(Text)
    illustrative: Mapped[bool] = mapped_column(Boolean, default=True)
    proposed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    __table_args__ = (UniqueConstraint("rule_id", "version"), CheckConstraint("effective_to >= effective_from"))


class RuleApproval(Identity, Base):
    __tablename__ = "rule_change_approvals"
    version_id: Mapped[str] = mapped_column(ForeignKey("rule_versions.id"), unique=True)
    approved_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str] = mapped_column(Text)


class SecurityDeposit(Identity, Base):
    __tablename__ = "security_deposits"
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    programme_id: Mapped[str] = mapped_column(ForeignKey("institution_programmes.id"))
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    rule_version_id: Mapped[str | None] = mapped_column(ForeignKey("rule_versions.id"), nullable=True)
    requirement_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    required_amount: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    regulatory_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    renewal_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    assigned_officer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Instrument(Identity, Base):
    __tablename__ = "deposit_instruments"
    deposit_id: Mapped[str] = mapped_column(ForeignKey("security_deposits.id"), index=True)
    instrument_type: Mapped[str] = mapped_column(String(30), default="FDR")
    bank: Mapped[str] = mapped_column(String(150))
    branch: Mapped[str] = mapped_column(String(150))
    number: Mapped[str] = mapped_column(String(100))
    depositor_name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Numeric(16, 2))
    issue_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date, index=True)
    validity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lien_details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="active")
    verification_status: Mapped[str] = mapped_column(String(40), default="pending")
    __table_args__ = (UniqueConstraint("bank", "number"), CheckConstraint("amount > 0"), CheckConstraint("maturity_date > issue_date"))


class Document(Identity, Base):
    __tablename__ = "documents"
    deposit_id: Mapped[str] = mapped_column(ForeignKey("security_deposits.id"), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("deposit_instruments.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    category: Mapped[str] = mapped_column(String(40), default="instrument")
    scan_status: Mapped[str] = mapped_column(String(40))
    processing_status: Mapped[str] = mapped_column(String(40), default="queued")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Extraction(Identity, Base):
    __tablename__ = "document_extractions"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), unique=True)
    method: Mapped[str] = mapped_column(String(40))
    original_text: Mapped[str] = mapped_column(Text)
    fields: Mapped[dict] = mapped_column(JSON)
    confidences: Mapped[dict] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(30), default='ocr', server_default='ocr')
    model_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    document_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warnings: Mapped[list] = mapped_column(JSON, default=list, server_default='[]')


class FieldCorrection(Identity, Base):
    __tablename__ = "field_corrections"
    extraction_id: Mapped[str] = mapped_column(ForeignKey("document_extractions.id"), index=True)
    field: Mapped[str] = mapped_column(String(60))
    original_value: Mapped[str] = mapped_column(Text)
    corrected_value: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Discrepancy(Identity, Base):
    __tablename__ = "discrepancy_cases"
    deposit_id: Mapped[str] = mapped_column(ForeignKey("security_deposits.id"), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("deposit_instruments.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    fields: Mapped[list] = mapped_column(JSON, default=list)
    evidence_source: Mapped[str] = mapped_column(String(150))
    next_step: Mapped[str] = mapped_column(Text)
    assigned_officer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open")
    response: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("deposit_id", "code"),)


class VerificationRequest(Identity, Base):
    __tablename__ = "verification_requests"
    deposit_id: Mapped[str] = mapped_column(ForeignKey("security_deposits.id"), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("deposit_instruments.id"))
    channel: Mapped[str] = mapped_column(String(100))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="pending")


class VerificationEvidence(Identity, Base):
    __tablename__ = "verification_evidence"
    request_id: Mapped[str] = mapped_column(ForeignKey("verification_requests.id"), unique=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str] = mapped_column(String(150))
    finding: Mapped[str] = mapped_column(String(30))
    observations: Mapped[str] = mapped_column(Text)
    confirmed_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_on: Mapped[date] = mapped_column(Date)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class MockBankRecord(Identity, Base):
    __tablename__ = "mock_bank_records"
    number: Mapped[str] = mapped_column(String(100), unique=True)
    fields: Mapped[dict] = mapped_column(JSON)
    available: Mapped[bool] = mapped_column(Boolean, default=True)


class Replacement(Identity, Base):
    __tablename__ = "instrument_replacements"
    deposit_id: Mapped[str] = mapped_column(ForeignKey("security_deposits.id"))
    previous_id: Mapped[str] = mapped_column(ForeignKey("deposit_instruments.id"), unique=True)
    replacement_id: Mapped[str] = mapped_column(ForeignKey("deposit_instruments.id"), unique=True)
    reason: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class ReleaseRequest(Identity, Base):
    __tablename__ = "release_requests"
    deposit_id: Mapped[str] = mapped_column(ForeignKey("security_deposits.id"), unique=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30), default="release")
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="under_review")
    workflow_snapshot: Mapped[dict] = mapped_column(JSON)
    decision_notes: Mapped[str] = mapped_column(Text, default="")
    authorised_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    completion_reference: Mapped[str] = mapped_column(String(150), default="")


class Clearance(Identity, Base):
    __tablename__ = "release_clearances"
    release_id: Mapped[str] = mapped_column(ForeignKey("release_requests.id"), index=True)
    cell: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    notes: Mapped[str] = mapped_column(Text, default="")
    officer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    __table_args__ = (UniqueConstraint("release_id", "cell"),)


class Notification(Identity, Base):
    __tablename__ = "notifications"
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    deposit_id: Mapped[str] = mapped_column(ForeignKey("security_deposits.id"))
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    email_status: Mapped[str] = mapped_column(String(40), default="simulated_outbox")


class NotificationRead(Base):
    __tablename__ = "notification_reads"
    notification_id: Mapped[str] = mapped_column(ForeignKey("notifications.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Configuration(Base):
    __tablename__ = "configuration"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class AuditChainHead(Base):
    __tablename__ = 'audit_chain_heads'
    entity_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_hash: Mapped[str] = mapped_column(String(64), default='')
    last_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Identity, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id"), nullable=True, index=True)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(80))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    previous_hash: Mapped[str] = mapped_column(String(64), default="")
    event_hash: Mapped[str] = mapped_column(String(64))


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def protect_audit(*_):
    raise ValueError("Audit events are append-only")
