"""Internal consistency of a receipt's figures.

A forger who raises the principal or extends the maturity date tends to leave the printed maturity value
as it was. Banks use different compounding conventions, so a value consistent with any common one passes.
"""
from datetime import date

TOLERANCE = 0.01  # relative; covers rounding and day-count differences between banks
PLAUSIBLE_RATE = (1.0, 15.0)  # % per year, used when the receipt prints no rate


def expected_values(principal, rate, years):
    r = rate / 100
    yield "simple interest", principal * (1 + r * years)
    for periods, name in ((1, "annual"), (2, "half-yearly"), (4, "quarterly"), (12, "monthly")):
        yield f"{name} compounding", principal * (1 + r / periods) ** (periods * years)


def maturity_problem(principal, value, issue, maturity, rate=None):
    """A plain-language description of the inconsistency, or None when the figures fit together."""
    principal, value = float(principal), float(value)
    issue, maturity = date.fromisoformat(str(issue)), date.fromisoformat(str(maturity))
    years = (maturity - issue).days / 365
    if years <= 0 or principal <= 0:
        return None
    if value <= principal:
        return f"The receipt's maturity value (INR {value:,.2f}) is not above its principal (INR {principal:,.2f})."
    if rate:
        options = list(expected_values(principal, float(rate), years))
        if all(abs(value - expected) / expected > TOLERANCE for _, expected in options):
            name, nearest = min(options, key=lambda option: abs(value - option[1]))
            return (f"The receipt's maturity value (INR {value:,.2f}) does not fit its principal (INR {principal:,.2f}), "
                    f"rate ({float(rate):g}%) and term ({(maturity - issue).days} days); {name} gives about INR {nearest:,.2f}.")
        return None
    implied = (value / principal - 1) / years * 100
    if not PLAUSIBLE_RATE[0] <= implied <= PLAUSIBLE_RATE[1]:
        return (f"The receipt's principal (INR {principal:,.2f}), maturity value (INR {value:,.2f}) and term imply "
                f"{implied:.1f}% a year, outside the usual range for a fixed deposit.")
    return None
