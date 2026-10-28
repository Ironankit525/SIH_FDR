from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(StrictModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class InstitutionInput(StrictModel):
    name: str = Field(min_length=3, max_length=200)
    state: str = Field(min_length=2, max_length=80)
    ownership: Literal["private", "government", "government_aided"] = "private"
    land_arrangement: Literal["owned", "private_lease"] = "owned"
    approval_year: int = Field(ge=1950, le=2100)
    contact_email: str = Field(min_length=5, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    address: str = Field(default="", max_length=2000)


class Registration(InstitutionInput):
    administrator_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    programme: str = Field(default="Engineering and Technology", min_length=2, max_length=100)
    level: Literal["undergraduate", "postgraduate", "diploma"] = "undergraduate"


class InstrumentInput(StrictModel):
    instrument_type: Literal["FDR", "RTGS", "SECURITY_DEPOSIT"] = "FDR"
    bank: str = Field(min_length=2, max_length=150)
    branch: str = Field(min_length=2, max_length=150)
    number: str = Field(min_length=4, max_length=100, pattern=r"^[A-Za-z0-9/_-]+$")
    depositor_name: str = Field(min_length=3, max_length=200)
    amount: float = Field(gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    issue_date: date
    maturity_date: date
    validity_date: date | None = None
    lien_details: str = Field(default="", max_length=2000)

    @field_validator("bank", "number")
    @classmethod
    def normalise(cls, v):
        return v.upper()

    @model_validator(mode="after")
    def dates(self):
        if self.maturity_date <= self.issue_date:
            raise ValueError("Maturity must be after the issue date")
        if self.issue_date > date.today():
            raise ValueError("Issue date cannot be in the future")
        if self.validity_date and self.validity_date < self.issue_date:
            raise ValueError("Validity cannot end before the issue date")
        return self


class DepositInput(InstrumentInput):
    programme_id: str
    regulatory_end_date: date | None = None
    renewal_due_date: date | None = None


class ReplacementInput(InstrumentInput):
    reason: str = Field(min_length=8, max_length=2000)


class RequirementInput(StrictModel):
    institution_id: str
    programme_id: str
    as_of: date = Field(default_factory=date.today)


class Note(StrictModel):
    notes: str = Field(min_length=5, max_length=4000)


class Correction(StrictModel):
    field: Literal["bank", "number", "depositor_name", "amount", "issue_date", "maturity_date"]
    corrected_value: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=5, max_length=2000)

    @model_validator(mode="after")
    def validate_corrected_field(self):
        if self.field == "amount":
            from decimal import Decimal, InvalidOperation
            try:
                value = Decimal(self.corrected_value.replace(",", ""))
                if not value.is_finite() or value <= 0 or value > Decimal("1000000000000"):
                    raise ValueError()
                self.corrected_value = str(value)
            except (InvalidOperation, ValueError):
                raise ValueError("Corrected amount must be a positive finite number")
        elif self.field.endswith("date"):
            try:
                date.fromisoformat(self.corrected_value)
            except ValueError:
                raise ValueError("Corrected dates must use YYYY-MM-DD")
        return self


class VerificationInput(StrictModel):
    channel: Literal["approved_bank_correspondence", "authorised_bank_portal", "branch_confirmation"]


class ForwardToBankInput(StrictModel):
    bank_name: str = Field(min_length=2, max_length=150)
    notes: str | None = Field(default=None, max_length=2000)


class ConfirmedFields(StrictModel):
    """What the bank itself stated, so it can be compared with the declaration rather than taken on trust."""
    bank: str | None = Field(default=None, max_length=150)
    number: str | None = Field(default=None, max_length=100)
    depositor_name: str | None = Field(default=None, max_length=200)
    amount: float | None = Field(default=None, gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    issue_date: date | None = None
    maturity_date: date | None = None


class BankDecisionInput(StrictModel):
    decision: Literal["verified", "rejected", "additional_info_required"]
    remarks: str = Field(min_length=5, max_length=4000)
    confirmed_fields: ConfirmedFields | None = None

    @model_validator(mode="after")
    def validate_remarks_by_decision(self):
        if self.decision in ("rejected", "additional_info_required") and len(self.remarks.strip()) < 10:
            raise ValueError(f"Please provide an explanation of at least 10 characters when selecting {self.decision.replace('_', ' ')}.")
        return self


class EvidenceInput(StrictModel):
    document_id: str
    source: str = Field(min_length=5, max_length=200)
    reference: str = Field(min_length=4, max_length=150)
    finding: Literal["confirmed", "mismatched", "inconclusive", "pending"]
    observations: str = Field(min_length=10, max_length=4000)
    verified_on: date
    confirmed_fields: ConfirmedFields | None = None

    @field_validator("verified_on")
    @classmethod
    def not_future(cls, v):
        if v > date.today():
            raise ValueError("Verification date cannot be in the future")
        return v

    @model_validator(mode="after")
    def confirmation_states_values(self):
        fields = self.confirmed_fields
        if self.finding == "confirmed" and not (fields and fields.amount and fields.maturity_date):
            raise ValueError("A confirmed finding must record at least the amount and maturity date the bank confirmed")
        return self


class AssignmentInput(StrictModel):
    officer_id: str | None = None  # None leaves the case unassigned
    reason: str = Field(min_length=10, max_length=2000)


class ReleaseInput(StrictModel):
    kind: Literal["release", "discharge", "refund"] = "release"
    reason: str = Field(min_length=10, max_length=4000)


class ResolutionReview(Note):
    decision: Literal["confirm", "reject"]


class Decision(Note):
    decision: Literal["approved", "rejected", "returned"]
    risk_acknowledged: bool = False


class Completion(StrictModel):
    reference: str = Field(min_length=5, max_length=150)


class WorkflowInput(StrictModel):
    cells: list[str] = Field(min_length=1, max_length=10)
    required_documents: list[Literal["release_request", "affidavit", "approval_letter"]] = Field(min_length=1)
    allow_mock_for_demo: bool = True
    require_regulatory_end: bool = True
    verification_max_age_days: int = Field(default=30, ge=1, le=365)
    coverage_warning_days: int = Field(default=60, ge=0, le=365)
    require_aicte_lien: bool = True

    @field_validator("cells")
    @classmethod
    def unique_cells(cls, values):
        if len(values) != len(set(values)) or any(not x or len(x) > 60 for x in values):
            raise ValueError("Clearance cells must be unique, nonempty names")
        return values


class AlertInput(StrictModel):
    reminder_days: list[int] = Field(min_length=1, max_length=12)
    escalation_days: int = Field(ge=1, le=90, default=7)

    @field_validator("reminder_days")
    @classmethod
    def valid_offsets(cls, values):
        if any(v < 0 or v > 365 for v in values) or len(set(values)) != len(values):
            raise ValueError("Use unique reminder offsets from 0 to 365 days")
        return sorted(values, reverse=True)


class RuleConfig(StrictModel):
    amounts: dict[str, float]
    exempt_ownership: list[Literal["government", "government_aided", "private"]] = []
    private_lease_multiplier: float = Field(ge=1, le=10, default=1)

    @field_validator("amounts")
    @classmethod
    def amounts_valid(cls, values):
        if not values or any(v < 0 or v > 1e12 for v in values.values()):
            raise ValueError("Provide nonnegative programme amounts")
        return values


class RuleInput(StrictModel):
    rule_id: str
    effective_from: date
    effective_to: date
    config: RuleConfig
    source_reference: str = Field(min_length=10, max_length=2000)
    illustrative: bool = True

    @model_validator(mode="after")
    def dates(self):
        if self.effective_to < self.effective_from:
            raise ValueError("Effective period is invalid")
        return self


class RiskPolicyInput(StrictModel):
    weights: dict[str, float] = Field(default_factory=dict)
    category_caps: dict[str, float] | None = None  # None keeps the default caps; {} removes every cap
    thresholds: dict[Literal["medium", "high", "critical"], int]

    @model_validator(mode="after")
    def valid_policy(self):
        from .risk import CATEGORIES, SIGNALS
        if set(self.weights) - set(SIGNALS) or any(not 0 <= v <= 0.95 for v in self.weights.values()):
            raise ValueError("Weights must name known signals and lie between 0 and 0.95")
        caps = self.category_caps or {}
        if set(caps) - set(CATEGORIES) or any(not 0 < v <= 1 for v in caps.values()):
            raise ValueError("Category caps must name known categories and lie between 0 and 1")
        t = self.thresholds
        if set(t) != {"medium", "high", "critical"} or not 0 < t["medium"] < t["high"] < t["critical"] < 100:
            raise ValueError("Thresholds must rise: 0 < medium < high < critical < 100")
        return self


class RiskWeightsInput(RiskPolicyInput):
    notes: str = Field(min_length=10, max_length=2000)


class UserInput(StrictModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=200)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["institution", "verification", "clearance", "authority", "admin", "auditor", "bank"]
    institution_id: str | None = None
    clearance_cell: str | None = None
    bank_name: str | None = None


class PasswordInput(StrictModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=12, max_length=128)
