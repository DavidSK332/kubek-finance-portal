"""Deterministic Decimal arithmetic. These are estimates, never bank approval."""
from decimal import Decimal, ROUND_HALF_UP, localcontext

ZERO = Decimal("0")


def dec(value):
    return Decimal(str(value))


def amount(value):
    return float(dec(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def ratio(numerator, denominator, multiplier=1):
    return amount(numerator / denominator * dec(multiplier)) if denominator > 0 else None


def monthly_payment(principal, annual_rate, years):
    principal, annual_rate = dec(principal), dec(annual_rate)
    months = int(years) * 12
    if principal < 0 or annual_rate < 0 or months <= 0:
        raise ValueError("Neplatné parametre úveru.")
    if principal == 0:
        return ZERO
    if annual_rate == 0:
        return (principal / months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    with localcontext() as context:
        context.prec = 40
        r = annual_rate / 100 / 12
        value = principal * r / (1 - (1 + r) ** -months)
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def financial_profile(data):
    income = sum((dec(data[k]) for k in (
        "income_employment", "income_business", "income_company", "income_other")), ZERO)
    debt = sum((dec(d["balance"]) for d in data["debts"]), ZERO)
    payments = sum((dec(d["payment"]) for d in data["debts"]), ZERO)
    unused = sum((max(ZERO, dec(d["limit"]) - dec(d["balance"]))
                  for d in data["debts"] if d["kind"] == "card"), ZERO)
    cashflow = income - dec(data["expenses"]) - payments
    spending = dec(data["expenses"]) + payments
    return {
        "income": amount(income), "annual_income": amount(income * 12),
        "debt": amount(debt), "payments": amount(payments),
        "expenses": amount(data["expenses"]), "disposable": amount(cashflow),
        "dti": ratio(debt, income * 12),
        "dti_with_limits": ratio(debt + unused * dec("0.20"), income * 12),
        "unused_credit": amount(unused),
        "debt_service_ratio": ratio(payments, income, 100),
        "reserve_months": ratio(dec(data["savings"]), spending),
    }


def compare_proposal(data, proposal):
    before = financial_profile(data)
    selected_ids = set(proposal["replace_ids"])
    known_ids = {d["id"] for d in data["debts"]}
    if not selected_ids <= known_ids:
        raise ValueError("Návrh obsahuje neznámy záväzok.")
    replaced = [d for d in data["debts"] if d["id"] in selected_ids]
    old_balance = sum((dec(d["balance"]) for d in replaced), ZERO)
    old_payment = sum((dec(d["payment"]) for d in replaced), ZERO)
    is_loan = proposal["kind"] in ("mortgage", "refinance")
    principal = dec(proposal["principal"]) if is_loan else ZERO
    if is_loan and principal < old_balance:
        raise ValueError("Nový úver musí pokryť zostatky vybraných záväzkov. Vlastné doplatenie tento model nezahŕňa.")
    payment = monthly_payment(principal, proposal["annual_rate"], proposal["years"]) if is_loan else ZERO
    payments_after = dec(before["payments"]) - old_payment + payment
    debt_after = dec(before["debt"]) - old_balance + principal
    extra_costs = dec(proposal["monthly_costs"])
    cash_after = dec(before["income"]) - dec(before["expenses"]) - payments_after - extra_costs
    change = cash_after - dec(before["disposable"])
    fees = dec(proposal["upfront_fees"])
    living_minimum = proposal.get("living_minimum")
    assessed = proposal.get("assessed_payments")
    dsti = None
    if living_minimum is not None and assessed is not None:
        dsti = ratio(dec(assessed), dec(before["income"]) - dec(living_minimum), 100)
    return {
        "loan_payment": amount(payment), "replaced_balance": amount(old_balance),
        "replaced_payment": amount(old_payment), "debt_after": amount(debt_after),
        "payments_after": amount(payments_after), "monthly_costs": amount(extra_costs),
        "disposable_after": amount(cash_after), "monthly_change": amount(change),
        "annual_change": amount(change * 12),
        "break_even_months": ratio(fees, change),
        "dti_after": ratio(debt_after, dec(before["annual_income"])),
        "debt_service_ratio_after": ratio(payments_after, dec(before["income"]), 100),
        "dsti_estimate": dsti,
        "loan_interest_estimate": amount(payment * proposal["years"] * 12 - principal) if is_loan else None,
        "loan_total_estimate": amount((payment + extra_costs) * proposal["years"] * 12 + fees) if is_loan else None,
        "upfront_fees": amount(fees),
    }


def document_checklist(data):
    documents = ["Doklad totožnosti - predložiť bezpečným spôsobom dohodnutým s agentom."]
    goals = set(data["goals"])
    if goals & {"mortgage", "refinance"}:
        documents += ["Potvrdenie o príjme alebo doklady podľa banky a typu príjmu.",
                      "Výpisy z účtu za obdobie požadované bankou.",
                      "Podklady k nehnuteľnosti a jej oceneniu podľa požiadaviek banky."]
    if data["debts"] and goals & {"mortgage", "refinance"}:
        documents += ["Aktuálne úverové zmluvy, zostatky a vyčíslenia predčasného splatenia."]
    if dec(data["income_business"]) > 0 or dec(data["income_company"]) > 0:
        documents += ["Daňové priznanie a účtovné podklady v rozsahu požadovanom bankou."]
    if goals & {"life", "property"}:
        documents += ["Existujúce poistné zmluvy a požiadavky na poistné krytie."]
    if "invest" in goals:
        documents += ["Investičný horizont, skúsenosti a tolerancia rizika - doplniť s oprávneným agentom."]
    return documents
