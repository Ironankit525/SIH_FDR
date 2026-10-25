from datetime import date
from sqlalchemy import select
from .models import RuleVersion


def calculate(db, institution, programme, as_of=None):
    as_of = as_of or date.today()
    version = db.scalar(select(RuleVersion).where(RuleVersion.status == "active", RuleVersion.effective_from <= as_of,
                                                RuleVersion.effective_to >= as_of).order_by(RuleVersion.effective_from.desc(), RuleVersion.version.desc()).limit(1))
    base = {"required_amount": None, "exempt": False, "manual_review": True, "rule_version_id": None,
            "illustrative": True, "source_reference": "No applicable approved rule", "effective_period": None,
            "explanation": "No applicable rule is configured. Refer this obligation for manual review."}
    if not version:
        return base
    base.update(rule_version_id=version.id, source_reference=version.source_reference, illustrative=version.illustrative,
                effective_period=f"{version.effective_from} to {version.effective_to}", version=version.version)
    if institution.ownership in version.config.get("exempt_ownership", []):
        base.update(required_amount=0, exempt=True, manual_review=version.illustrative,
                    explanation=f"Ownership '{institution.ownership}' is exempt under this configured rule. Verify institutional classification.")
        return base
    key = f"{programme.name}|{programme.level}"
    amount = version.config.get("amounts", {}).get(key)
    if amount is None:
        base["explanation"] = "This programme and level are not covered by the configured rule. Manual determination is required."
        return base
    multiplier = version.config.get("private_lease_multiplier", 1) if institution.land_arrangement == "private_lease" else 1
    base.update(required_amount=round(amount * multiplier, 2), manual_review=version.illustrative,
                explanation=f"Configured base INR {amount:,.0f} × land arrangement multiplier {multiplier}. " +
                ("Illustrative example; an authorised officer must confirm applicability." if version.illustrative else "Apply alongside the recorded source and any case-specific conditions."))
    return base
